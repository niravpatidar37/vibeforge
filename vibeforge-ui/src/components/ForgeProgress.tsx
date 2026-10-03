import type { ProgressEvent } from '../types'

type StepState = 'pending' | 'active' | 'done'

interface Step {
  key: string
  label: string
  state: StepState
  detail?: string
}

/** Fold the raw LangGraph SSE events into four human steps. */
function stepsFrom(events: ProgressEvent[], busy: boolean): Step[] {
  const seen = (node: string) => events.some(e => e.node === node)
  const last = <K extends string>(node: K) => [...events].reverse().find(e => e.node === node)

  const mood = last('analyse_mood')?.data
  const critique = last('critique_playlist')?.data
  const curateRounds = events.filter(e => e.node === 'curate_playlist').length
  const finished = seen('finalise') || seen('done')

  const moodDetail = mood?.emotion
    ? [mood.emotion, mood.energy && `${mood.energy} energy`, mood.bpm_range && `${mood.bpm_range} BPM`, mood.occasion]
        .filter(Boolean)
        .join(' · ')
    : undefined
  const criticDetail =
    typeof critique?.score === 'number'
      ? `${critique.score}/10 · ${critique.score >= 7 ? 'it fits, keep it' : 'sent back for another pass'}`
      : undefined

  const raw: Omit<Step, 'state'>[] = [
    { key: 'listen', label: 'Listening to how you feel', detail: moodDetail },
    { key: 'dig', label: 'Digging through the crates', detail: curateRounds > 1 ? `Take ${curateRounds}` : undefined },
    { key: 'critic', label: 'Getting a second opinion', detail: criticDetail },
    { key: 'press', label: 'Pressing the record', detail: finished ? 'Done' : undefined },
  ]
  const doneFlags = [seen('analyse_mood'), seen('curate_playlist'), seen('critique_playlist'), finished]
  // The step after the last completed one is in progress; refinement loops reopen "dig".
  const lastEvent = events[events.length - 1]?.node
  let activeIdx = doneFlags.findIndex(d => !d)
  if (lastEvent === 'increment_attempts' || (lastEvent === 'critique_playlist' && (critique?.score ?? 10) < 7)) activeIdx = 1
  return raw.map((s, i) => ({
    ...s,
    state: busy && i === activeIdx ? 'active' : doneFlags[i] && !(busy && i === activeIdx) ? 'done' : 'pending',
  }))
}

export default function ForgeProgress({ events, busy }: { events: ProgressEvent[]; busy: boolean }) {
  const steps = stepsFrom(events, busy)
  return (
    <ol className="forge-steps" aria-label="Studio session progress" aria-live="polite">
      {steps.map((s, i) => (
        <li key={s.key} className={`forge-step is-${s.state}`}>
          <span className="forge-dot" aria-hidden="true">{s.state === 'done' ? '✓' : i + 1}</span>
          <span className="forge-label">{s.label}</span>
          {s.detail && <span className="forge-detail">{s.detail}</span>}
          <span className="sr-only">{s.state === 'done' ? 'complete' : s.state === 'active' ? 'in progress' : 'waiting'}</span>
        </li>
      ))}
    </ol>
  )
}
