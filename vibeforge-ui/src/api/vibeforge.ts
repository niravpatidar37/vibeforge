import type { Mode, Playlist, ProgressEvent, Track } from '../types'
import { isPlaylist } from '../lib/validate'

/** API origin. Override at build time with VITE_API_BASE; never put secrets in VITE_* vars (they ship to the browser). */
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') || 'http://localhost:8000'

export interface GenerateParams {
  mood: string
  context: string
  seed: string
  model: string
  mode: Mode
  spotify_enrich: boolean
}

async function errorFrom(res: Response, fallback: string): Promise<Error> {
  const body = await res.json().catch(() => null) as { detail?: unknown } | null
  const detail = typeof body?.detail === 'string' ? body.detail : null
  return new Error(detail ?? `${fallback} (${res.status})`)
}

export async function fetchModels(signal?: AbortSignal): Promise<string[]> {
  const res = await fetch(`${API_BASE}/models`, { signal })
  if (!res.ok) throw await errorFrom(res, 'Could not load models')
  const data: unknown = await res.json()
  if (!Array.isArray(data) || !data.every(m => typeof m === 'string')) throw new Error('Unexpected models response')
  return data
}

export async function generatePlaylist(params: GenerateParams, signal?: AbortSignal): Promise<Playlist> {
  const res = await fetch(`${API_BASE}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
    signal,
  })
  if (!res.ok) throw await errorFrom(res, 'Generation failed')
  const data: unknown = await res.json()
  if (!isPlaylist(data)) throw new Error('The server returned a playlist VibeForge could not read')
  return data
}

export async function enrichPlaylist(playlist: Playlist, signal?: AbortSignal): Promise<Playlist> {
  const res = await fetch(`${API_BASE}/enrich`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(playlist),
    signal,
  })
  if (!res.ok) throw await errorFrom(res, 'Link enrichment failed')
  const data: unknown = await res.json()
  if (!isPlaylist(data)) throw new Error('Unexpected enrichment response')
  return data
}

export async function saveFeedback(loved: Track[], disliked: Track[]): Promise<void> {
  // Mirrors api.py FeedbackTrack: title + artist only, each 1..200 chars.
  const strip = (t: Track) => ({ title: t.title.slice(0, 200), artist: t.artist.slice(0, 200) })
  const res = await fetch(`${API_BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ loved: loved.map(strip), disliked: disliked.map(strip) }),
  })
  if (!res.ok) throw await errorFrom(res, 'Could not save your taste')
}

/** Agentic mode over Server-Sent Events. Returns a cancel function. */
export function streamPlaylist(
  params: Omit<GenerateParams, 'mode'>,
  handlers: {
    onEvent: (evt: ProgressEvent) => void
    onPlaylist: (pl: Playlist) => void
    onError: (msg: string) => void
    onDone: () => void
  },
): () => void {
  const qs = new URLSearchParams({
    mood: params.mood,
    context: params.context,
    seed: params.seed,
    model: params.model,
    spotify_enrich: String(params.spotify_enrich),
  })
  const es = new EventSource(`${API_BASE}/stream?${qs}`)
  let finished = false
  const finish = () => {
    finished = true
    es.close()
  }

  es.onmessage = (e: MessageEvent<string>) => {
    let evt: ProgressEvent
    try {
      evt = JSON.parse(e.data) as ProgressEvent
    } catch {
      return // ignore malformed frames rather than crash
    }
    if (typeof evt?.node !== 'string') return
    if (evt.node === 'error') {
      handlers.onError(typeof evt.message === 'string' ? evt.message : 'The studio hit a problem')
      finish()
      return
    }
    handlers.onEvent(evt)
    if (evt.node === 'finalise' && evt.data) {
      if (isPlaylist(evt.data)) handlers.onPlaylist(evt.data)
      else handlers.onError('The server returned a playlist VibeForge could not read')
    }
    if (evt.node === 'done') {
      handlers.onDone()
      finish()
    }
  }

  es.onerror = () => {
    if (finished) return
    handlers.onError('Lost the connection to the VibeForge server')
    finish()
  }

  return finish
}
