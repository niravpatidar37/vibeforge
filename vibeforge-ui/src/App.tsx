import { useEffect, useRef, useState } from 'react'
import type { Playlist, Mode, ProgressEvent } from './types'
import { enrichPlaylist, fetchModels, generatePlaylist, streamPlaylist } from './api/vibeforge'
import MoodForm from './components/MoodForm'
import PlaylistCard from './components/PlaylistCard'
import ProgressLog from './components/ProgressLog'
import FeedbackPanel from './components/FeedbackPanel'
import './App.css'
import './index.css'

function estimateGenerationMs(mode: Mode, model: string): number {
  if (model.startsWith('hf:')) {
    return mode === 'fast' ? 50000 : mode === 'deep' ? 100000 : 90000
  }
  return mode === 'fast' ? 8000 : mode === 'deep' ? 16000 : 30000
}

export default function App() {
  const [models, setModels] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [playlist, setPlaylist] = useState<Playlist | null>(null)
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [estimatedMs, setEstimatedMs] = useState(8000)
  const startedAt = useRef<number | null>(null)

  useEffect(() => {
    if (!loading || startedAt.current === null) return
    const timer = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAt.current!)
    }, 100)
    return () => window.clearInterval(timer)
  }, [loading])

  useEffect(() => {
    fetchModels().then(setModels).catch(() => setModels(['llama-3.3-70b-versatile']))
  }, [])

  const handleSubmit = async (params: {
    mood: string; context: string; seed: string
    model: string; mode: Mode; spotify_enrich: boolean
  }) => {
    setLoading(true)
    setPlaylist(null)
    setEvents([])
    setError(null)
    startedAt.current = Date.now()
    setElapsedMs(0)
    setEstimatedMs(estimateGenerationMs(params.mode, params.model))

    const finish = () => {
      if (startedAt.current !== null) setElapsedMs(Date.now() - startedAt.current)
      setLoading(false)
    }

    if (params.mode === 'agentic') {
      streamPlaylist({
        ...params,
        onEvent: (evt) => setEvents(prev => [...prev, evt]),
        onPlaylist: (pl) => {
          setPlaylist(pl)
          finish()
        },
        onError: (msg) => { setError(msg); finish() },
      })
    } else {
      try {
        const pl = await generatePlaylist(params as any)
        setPlaylist(pl)
        if (params.spotify_enrich) enrichPlaylist(pl).then(setPlaylist).catch(() => {})
      } catch (e: any) {
        setError(e.message ?? 'Something went wrong')
      } finally {
        finish()
      }
    }
  }

  const handleFeedback = async (loved: any[], disliked: any[]) => {
    await fetch('http://localhost:8000/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ loved, disliked }),
    }).catch(() => {})
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="VibeForge home">
          <img className="brand-mark" src="/favicon.svg" alt="" width="28" height="28" />
          <span>VibeForge</span>
        </a>
        <span className="topbar-status"><span className="status-dot" /> studio mode</span>
      </header>

      <main className="workspace">
        <section className="intro-panel">
          <p className="eyebrow">01 / mood to mix</p>
          <h1>Give the feeling<br /><em>a soundtrack.</em></h1>
          <p className="intro-copy">Tell us where your head is at. VibeForge turns the details into a playlist with texture, momentum, and a little left field magic.</p>
          <div className="signal-strip">
            <div><strong>10</strong><span>tracks per mix</span></div>
            <div><strong>∞</strong><span>moods welcome</span></div>
            <div><strong>AI</strong><span>curated in real time</span></div>
          </div>
        </section>

        <section className="form-panel">
          <div className="panel-heading">
            <span className="panel-kicker">Start with a signal</span>
            <span className="panel-index">A</span>
          </div>
          <MoodForm models={models} loading={loading} onSubmit={handleSubmit} />
          {(loading || elapsedMs > 0) && (
            <div className="generation-clock" aria-live="polite">
              <span className={`clock-pulse ${loading ? 'is-active' : ''}`} />
              <span>{loading ? 'Forging your mix' : 'Ready'}</span>
              <strong>{(elapsedMs / 1000).toFixed(1)}s</strong>
              <small>{loading ? `~${Math.max(0, Math.ceil((estimatedMs - elapsedMs) / 1000))}s left` : 'actual generation time'}</small>
            </div>
          )}
        </section>

        {/* Error */}
        {error && (
          <div className="error-banner">
            <span>!</span> {error}
          </div>
        )}

        {/* Agentic progress */}
        {events.length > 0 && <section className="result-section"><ProgressLog events={events} /></section>}

        {/* Playlist result */}
        {playlist && (
          <section className="result-section">
            <PlaylistCard playlist={playlist} />
            <FeedbackPanel tracks={playlist.tracks} onSave={handleFeedback} />
          </section>
        )}
      </main>
      <footer className="footer-line"><span>VibeForge / personal radio for right now</span><span>Made for the in-between moments</span></footer>
    </div>
  )
}
