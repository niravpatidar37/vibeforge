/**
 * Track links come from model output and from the Spotify API, so they're untrusted.
 * Only render https links to the music hosts VibeForge actually produces; anything else
 * (javascript:, data:, look-alike hosts, plain http) is dropped instead of rendered.
 */
const ALLOWED_HOSTS = new Set([
  'open.spotify.com',
  'www.youtube.com',
  'youtube.com',
  'm.youtube.com',
  'music.youtube.com',
])

export function safeMusicUrl(raw: unknown): string | null {
  if (typeof raw !== 'string' || raw.length === 0 || raw.length > 2048) return null
  let url: URL
  try {
    url = new URL(raw)
  } catch {
    return null
  }
  if (url.protocol !== 'https:') return null
  if (url.username || url.password) return null
  if (!ALLOWED_HOSTS.has(url.hostname.toLowerCase())) return null
  return url.toString()
}
