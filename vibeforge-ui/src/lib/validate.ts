import type { Playlist, Track } from '../types'

/**
 * Runtime shape checks for data coming back from the API / SSE stream.
 * TypeScript types vanish at runtime; a malformed or hostile payload should
 * surface as an error, not crash rendering halfway through.
 */
const isStr = (v: unknown, max = 500): v is string => typeof v === 'string' && v.length <= max

function isTrack(v: unknown): v is Track {
  if (typeof v !== 'object' || v === null) return false
  const t = v as Record<string, unknown>
  return (
    isStr(t.title, 300) &&
    isStr(t.artist, 300) &&
    isStr(t.genre, 120) &&
    (t.bpm === null || t.bpm === undefined || (typeof t.bpm === 'number' && Number.isFinite(t.bpm))) &&
    (t.spotify_search_url === undefined || isStr(t.spotify_search_url, 2048)) &&
    (t.youtube_search_url === undefined || isStr(t.youtube_search_url, 2048))
  )
}

export function isPlaylist(v: unknown): v is Playlist {
  if (typeof v !== 'object' || v === null) return false
  const p = v as Record<string, unknown>
  return (
    isStr(p.name, 200) &&
    isStr(p.mood_summary, 1000) &&
    Array.isArray(p.vibe_tags) && p.vibe_tags.every(tag => isStr(tag, 60)) &&
    (p.energy_level === 'low' || p.energy_level === 'medium' || p.energy_level === 'high') &&
    Array.isArray(p.genres) && p.genres.every(g => isStr(g, 120)) &&
    Array.isArray(p.tracks) && p.tracks.length > 0 && p.tracks.length <= 20 && p.tracks.every(isTrack)
  )
}
