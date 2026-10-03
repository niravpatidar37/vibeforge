import { useCallback, useEffect, useRef, useState } from 'react'
import type { Mode, Playlist, ProgressEvent, Track } from './types'
import type { GenerateParams } from './api/vibeforge'
import { enrichPlaylist, fetchModels, generatePlaylist, saveFeedback, streamPlaylist } from './api/vibeforge'
import { IDLE_PALETTE, sleeveFor } from './lib/sleeve'
import { PickMark, Wordmark } from './components/Logo'
import Turntable from './components/Turntable'
import MoodComposer from './components/MoodComposer'
import ForgeProgress from './components/ForgeProgress'
import PressedRecord from './components/PressedRecord'
import './App.css'

type Status = 'idle' | 'forging' | 'ready' | 'error'
type ApiStatus = 'checking' | 'online' | 'offline'

function estimateMs(mode: Mode, model: string): number {
  if (model.startsWith('hf:')) return mode === 'fast' ? 50000 : mode === 'deep' ? 100000 : 90000
  return mode === 'fast' ? 8000 : mode === 'deep' ? 16000 : 30000
}

export default function App() {
  const [models, setModels] = useState<string[]>([])
  const [api, setApi] = useState<ApiStatus>('checking')
  const [status, setStatus] = useState<Status>('idle')
  const [mode, setMode] = useState<Mode>('fast')
  const [playlist, setPlaylist] = useState<Playlist | null>(null)
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [estimate, setEstimate] = useState(8000)
  const startedAt = useRef(0)
  const cancelRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    fetchModels(ctrl.signal)
      .then(m => { setModels(m); setApi('online') })
      .catch(() => {
        if (ctrl.signal.aborted) return
        setApi('offline')
        setModels(['llama-3.3-70b-versatile'])
      })
    return () => ctrl.abort()
  }, [])

  useEffect(() => {
    if (status !== 'forging') return
    const t = window.setInterval(() => setElapsed(Date.now() - startedAt.current), 100)
    return () => window.clearInterval(t)
  }, [status])

  // Cancel any in-flight request when the page goes away.
  useEffect(() => () => cancelRef.current?.(), [])

  useEffect(() => {
    if (status === 'ready') document.getElementById('pressed-title')?.focus()
  }, [status])

  const finish = useCallback((next: Status) => {
    setElapsed(Date.now() - startedAt.current)
    setStatus(next)
    cancelRef.current = null
  }, [])

  const handleSubmit = (params: GenerateParams) => {
    cancelRef.current?.()
    setStatus('forging')
    setMode(params.mode)
    setPlaylist(null)
    setEvents([])
    setError(null)
    startedAt.current = Date.now()
    setElapsed(0)
    setEstimate(estimateMs(params.mode, params.model))

    if (params.mode === 'agentic') {
      let got: Playlist | null = null
      const { mood, context, seed, model, spotify_enrich } = params
      cancelRef.current = streamPlaylist({ mood, context, seed, model, spotify_enrich }, {
        onEvent: evt => setEvents(prev => [...prev, evt]),
        onPlaylist: pl => { got = pl; setPlaylist(pl) },
        onError: msg => { setError(msg); finish(got ? 'ready' : 'error') },
        onDone: () => finish(got ? 'ready' : 'error'),
      })
      return
    }

    const ctrl = new AbortController()
    cancelRef.current = () => ctrl.abort()
    generatePlaylist(params, ctrl.signal)
      .then(pl => {
        setPlaylist(pl)
        finish('ready')
        if (params.spotify_enrich) {
          // Non-blocking: upgrade search links to direct track links when they arrive.
          enrichPlaylist(pl, ctrl.signal).then(setPlaylist).catch(() => {})
        }
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return
        setError(e instanceof Error ? e.message : 'Something went wrong')
        finish('error')
      })
  }

  const handleCancel = () => {
    cancelRef.current?.()
    cancelRef.current = null
    setStatus(playlist ? 'ready' : 'idle')
    setError(null)
  }

  const handleSaveTaste = (loved: Track[], skipped: Track[]) => saveFeedback(loved, skipped)

  const deckState = status === 'forging' ? 'forging' : status === 'ready' ? 'ready' : 'idle'
  const palette = playlist ? sleeveFor(playlist).palette : IDLE_PALETTE
  const secs = (elapsed / 1000).toFixed(1)
  const left = Math.max(0, Math.ceil((estimate - elapsed) / 1000))

  return (
    <div className="app">
      <header className="masthead">
        <a className="brand" href="/" aria-label="VibeForge home">
          <PickMark size={34} />
          <Wordmark />
        </a>
        <p className={`api-status is-${api}`} role="status">
          <span className="api-dot" aria-hidden="true" />
          {api === 'online' && 'Studio is open'}
          {api === 'checking' && 'Warming up the studio…'}
          {api === 'offline' && (
            <>Studio offline · start it with <code>uv run uvicorn api:app --port 8000</code></>
          )}
        </p>
      </header>

      <main>
        <section className="stage">
          <div className="deck">
            <Turntable state={deckState} palette={palette} />
            <div className="deck-caption" aria-live="polite">
              {status === 'idle' && <p>The needle's up. Tell it how you feel.</p>}
              {status === 'forging' && mode !== 'agentic' && (
                <p>
                  Listening… <strong>{secs}s</strong> <span className="muted">· about {left}s left</span>
                </p>
              )}
              {status === 'ready' && playlist && (
                <p>
                  Now playing <strong>{playlist.name}</strong> <span className="muted">· pressed in {secs}s</span>
                </p>
              )}
              {status === 'error' && <p>The needle skipped.</p>}
            </div>
            {mode === 'agentic' && (status === 'forging' || events.length > 0) && (
              <ForgeProgress events={events} busy={status === 'forging'} />
            )}
          </div>

          <div className="composer-col">
            <MoodComposer models={models} busy={status === 'forging'} onSubmit={handleSubmit} onCancel={handleCancel} />
            {error && (
              <p className="alert" role="alert">
                <strong>That didn't press.</strong> {error}
              </p>
            )}
          </div>
        </section>

        {playlist && status !== 'forging' && (
          <PressedRecord key={`${playlist.name}-${startedAt.current}`} playlist={playlist} onSaveTaste={handleSaveTaste} />
        )}
      </main>

      <footer className="colophon">
        <span>VibeForge · fall in love with music again</span>
        <span>Track picks are AI-generated. Links open Spotify and YouTube.</span>
      </footer>
    </div>
  )
}
