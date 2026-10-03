import { useEffect, useId, useState } from 'react'
import type { Mode } from '../types'
import type { GenerateParams } from '../api/vibeforge'
import { PickMark } from './Logo'

// Mirrors the server-side Pydantic caps in api.py / application.py.
const MAX_MOOD = 500
const MAX_CONTEXT = 500
const MAX_SEED = 200

const STARTERS = [
  "3am, can't sleep, thinking about everything",
  'First date nerves, getting ready',
  'Rainy Sunday, coffee, nowhere to be',
  'Driving home after good news, windows down',
  'Desi wedding, the dance floor just opened',
  'Missing someone who lives far away',
]

const MODES: { value: Mode; label: string; desc: string }[] = [
  { value: 'fast', label: 'Quick press', desc: 'One pass. About 5–10 seconds.' },
  { value: 'deep', label: 'Deep listen', desc: 'Reads the mood first, then curates.' },
  { value: 'agentic', label: 'Studio session', desc: 'A critic reviews and sends it back until it fits. Live progress.' },
]

interface Props {
  models: string[]
  busy: boolean
  onSubmit: (params: GenerateParams) => void
  onCancel: () => void
}

export default function MoodComposer({ models, busy, onSubmit, onCancel }: Props) {
  const [mood, setMood] = useState('')
  const [context, setContext] = useState('')
  const [seed, setSeed] = useState('')
  const [model, setModel] = useState(models[0] ?? '')
  const [mode, setMode] = useState<Mode>('fast')
  const [spotify, setSpotify] = useState(true)
  const ids = useId()

  useEffect(() => {
    if (models.length > 0 && !models.includes(model)) setModel(models[0])
  }, [models, model])

  const canSubmit = mood.trim().length > 0 && !busy && model.length > 0

  const submit = () => {
    if (!canSubmit) return
    onSubmit({ mood: mood.trim(), context: context.trim(), seed: seed.trim(), model, mode, spotify_enrich: spotify })
  }

  return (
    <form
      className="composer"
      onSubmit={e => {
        e.preventDefault()
        submit()
      }}
    >
      <p className="eyebrow">Side A · tonight</p>
      <h1 className="composer-title">
        What does tonight <em>feel</em> like?
      </h1>
      <p className="composer-lede">
        Write it the way you'd tell a friend. VibeForge listens, digs through the crates, and presses ten
        tracks that fit.
      </p>

      <label className="sr-only" htmlFor={`${ids}-mood`}>Describe your mood</label>
      <div className="letter">
        <textarea
          id={`${ids}-mood`}
          value={mood}
          maxLength={MAX_MOOD}
          rows={3}
          placeholder="Driving home after good news, windows down, a little in disbelief…"
          onChange={e => setMood(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault()
              submit()
            }
          }}
        />
        <span className="letter-count" aria-live="off">{mood.length} / {MAX_MOOD}</span>
      </div>

      <div className="starters" role="group" aria-label="Need a starting point?">
        {STARTERS.map(s => (
          <button key={s} type="button" className="starter" onClick={() => setMood(s)}>
            {s}
          </button>
        ))}
      </div>

      <details className="finetune">
        <summary>
          <span>Fine-tune the pressing</span>
          <small>{MODES.find(m => m.value === mode)?.label} · {model || 'loading models…'}</small>
        </summary>

        <div className="finetune-grid">
          <label className="field">
            <span>A song that's close <i>optional</i></span>
            <input value={seed} maxLength={MAX_SEED} onChange={e => setSeed(e.target.value)} placeholder="Blinding Lights by The Weeknd" />
          </label>
          <label className="field">
            <span>Where you are <i>optional</i></span>
            <input value={context} maxLength={MAX_CONTEXT} onChange={e => setContext(e.target.value)} placeholder="Late train, studying, rain outside" />
          </label>
        </div>

        <fieldset className="modes">
          <legend>How carefully should it listen?</legend>
          {MODES.map(m => (
            <label key={m.value} className={`mode ${mode === m.value ? 'is-on' : ''}`}>
              <input type="radio" name={`${ids}-mode`} value={m.value} checked={mode === m.value} onChange={() => setMode(m.value)} />
              <strong>{m.label}</strong>
              <span>{m.desc}</span>
            </label>
          ))}
        </fieldset>

        <div className="finetune-row">
          <label className="field">
            <span>Model</span>
            <select value={model} onChange={e => setModel(e.target.value)} disabled={models.length === 0}>
              {models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <label className="switch">
            <input type="checkbox" checked={spotify} onChange={e => setSpotify(e.target.checked)} />
            <span className="switch-track" aria-hidden="true" />
            <span>Find direct Spotify links</span>
          </label>
        </div>
      </details>

      <div className="press-row">
        <button type="submit" className="press" disabled={!canSubmit}>
          <PickMark size={22} />
          {busy ? 'Pressing your record…' : 'Press my record'}
        </button>
        {busy ? (
          <button type="button" className="ghost" onClick={onCancel}>Stop</button>
        ) : (
          <span className="press-hint"><kbd>Ctrl</kbd> + <kbd>Enter</kbd></span>
        )}
      </div>
    </form>
  )
}
