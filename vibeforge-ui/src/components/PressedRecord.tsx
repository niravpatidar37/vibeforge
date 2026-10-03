import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import type { Playlist, Track } from '../types'
import { sleeveFor } from '../lib/sleeve'
import { safeMusicUrl } from '../lib/safeUrl'
import SleeveArt from './SleeveArt'

type Rating = 'love' | 'skip'
type SaveState = 'idle' | 'saving' | 'saved' | 'error'

interface Props {
  playlist: Playlist
  onSaveTaste: (loved: Track[], skipped: Track[]) => Promise<void>
}

const ENERGY_WORD = { low: 'Low', medium: 'Medium', high: 'High' } as const

/** Heart that beats at the track's tempo. Clamped so a bad BPM can't strobe. */
function beatStyle(bpm: number | null): CSSProperties | undefined {
  if (!bpm || !Number.isFinite(bpm)) return undefined
  const clamped = Math.min(200, Math.max(50, bpm))
  return { ['--beat' as string]: `${(60 / clamped).toFixed(3)}s` }
}

function TrackRow({ track, n, rating, onRate }: {
  track: Track
  n: number
  rating: Rating | undefined
  onRate: (r: Rating) => void
}) {
  const spotify = safeMusicUrl(track.spotify_search_url)
  const youtube = safeMusicUrl(track.youtube_search_url)
  return (
    <li className={`track ${rating ? `is-${rating}` : ''}`}>
      <span className="track-n">{String(n).padStart(2, '0')}</span>
      <span className="track-main">
        <span className="track-title">{track.title}</span>
        <span className="track-artist">{track.artist}</span>
        <span className="track-meta">
          <span className={`beat ${track.bpm ? '' : 'is-still'}`} style={beatStyle(track.bpm)} aria-hidden="true" />
          <span className="track-genre">{track.genre}</span>
          {track.bpm ? <span className="track-bpm">{track.bpm} bpm</span> : null}
        </span>
      </span>
      <span className="track-actions">
        {spotify && (
          <a className="listen" href={spotify} target="_blank" rel="noopener noreferrer" aria-label={`Listen to ${track.title} on Spotify`}>
            Spotify
          </a>
        )}
        {youtube && (
          <a className="listen" href={youtube} target="_blank" rel="noopener noreferrer" aria-label={`Find ${track.title} on YouTube`}>
            YouTube
          </a>
        )}
        <button
          type="button"
          className="rate rate-love"
          aria-pressed={rating === 'love'}
          aria-label={`Love ${track.title}`}
          onClick={() => onRate('love')}
        >
          ♥
        </button>
        <button
          type="button"
          className="rate rate-skip"
          aria-pressed={rating === 'skip'}
          aria-label={`Not for me: ${track.title}`}
          onClick={() => onRate('skip')}
        >
          ✕
        </button>
      </span>
    </li>
  )
}

export default function PressedRecord({ playlist, onSaveTaste }: Props) {
  const design = useMemo(() => sleeveFor(playlist), [playlist])
  const [ratings, setRatings] = useState<Record<number, Rating>>({})
  const [save, setSave] = useState<SaveState>('idle')
  const [saveError, setSaveError] = useState('')

  const rate = (i: number, r: Rating) => {
    setSave(s => (s === 'saved' ? 'idle' : s))
    setRatings(prev => {
      const next = { ...prev }
      if (next[i] === r) delete next[i]
      else next[i] = r
      return next
    })
  }

  const loved = playlist.tracks.filter((_, i) => ratings[i] === 'love')
  const skipped = playlist.tracks.filter((_, i) => ratings[i] === 'skip')
  const half = Math.ceil(playlist.tracks.length / 2)
  const sides: { label: string; from: number; tracks: Track[] }[] = [
    { label: 'Side A', from: 0, tracks: playlist.tracks.slice(0, half) },
    { label: 'Side B', from: half, tracks: playlist.tracks.slice(half) },
  ]

  const handleSave = async () => {
    setSave('saving')
    setSaveError('')
    try {
      await onSaveTaste(loved, skipped)
      setSave('saved')
    } catch (e) {
      setSave('error')
      setSaveError(e instanceof Error ? e.message : 'Could not save your taste')
    }
  }

  return (
    <article className="pressed" aria-labelledby="pressed-title">
      <div className="sleeve-col">
        <div
          className="sleeve-stack"
          style={{ ['--label' as string]: design.palette.fg, ['--sleeve-bg' as string]: design.palette.bg } as CSSProperties}
        >
          <div className="sleeve-vinyl" aria-hidden="true" />
          <figure className="sleeve" style={{ color: design.palette.text }}>
            <SleeveArt design={design} className="sleeve-art" />
            <figcaption className="sleeve-type">
              <span className="sleeve-brand">VibeForge · {ENERGY_WORD[playlist.energy_level]} energy</span>
              <span className="sleeve-name">{playlist.name}</span>
            </figcaption>
          </figure>
        </div>
      </div>

      <div className="liner">
        <p className="eyebrow">Freshly pressed · {playlist.tracks.length} tracks</p>
        <h2 id="pressed-title" className="pressed-title" tabIndex={-1}>{playlist.name}</h2>
        <p className="pressed-summary">{playlist.mood_summary}</p>
        <p className="pressed-tags">
          {playlist.vibe_tags.map(t => <span key={t}>#{t}</span>)}
          {playlist.genres.length > 0 && <span className="pressed-genres">{playlist.genres.join(' · ')}</span>}
        </p>

        <div className="sides">
          {sides.map(side => side.tracks.length > 0 && (
            <section key={side.label} className="side" aria-label={side.label}>
              <h3 className="side-label">{side.label}</h3>
              <ol className="tracks" start={side.from + 1}>
                {side.tracks.map((t, j) => {
                  const i = side.from + j
                  return <TrackRow key={`${i}-${t.title}`} track={t} n={i + 1} rating={ratings[i]} onRate={r => rate(i, r)} />
                })}
              </ol>
            </section>
          ))}
        </div>

        <div className="taste-bar" role="region" aria-label="Teach VibeForge your taste">
          <p className="taste-status" aria-live="polite">
            {save === 'saved'
              ? 'Saved. Your next record will know you a little better.'
              : save === 'error'
                ? saveError
                : loved.length + skipped.length === 0
                  ? 'Tap ♥ on the songs that got you. ✕ the ones that didn’t.'
                  : `${loved.length} loved · ${skipped.length} not for you`}
          </p>
          <div className="taste-actions">
            <button type="button" className="ghost" onClick={() => setRatings(Object.fromEntries(playlist.tracks.map((_, i) => [i, 'love' as Rating])))}>
              Love them all
            </button>
            {loved.length + skipped.length > 0 && (
              <button type="button" className="ghost" onClick={() => setRatings({})}>Clear</button>
            )}
            <button
              type="button"
              className="press press-small"
              disabled={loved.length + skipped.length === 0 || save === 'saving' || save === 'saved'}
              onClick={handleSave}
            >
              {save === 'saving' ? 'Saving…' : save === 'saved' ? 'Saved ♥' : 'Remember my taste'}
            </button>
          </div>
        </div>
      </div>
    </article>
  )
}
