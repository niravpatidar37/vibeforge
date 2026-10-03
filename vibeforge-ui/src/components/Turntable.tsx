import type { SleevePalette } from '../lib/sleeve'
import { BeamedNotes } from './Logo'

export type DeckState = 'idle' | 'forging' | 'ready'

/**
 * The turntable. The record spins at 33⅓ rpm while VibeForge is pressing, the
 * tonearm swings in, and the label takes on the colours of the finished sleeve.
 * Purely presentational: aria-hidden, the caption carries the state for screen readers.
 */
export default function Turntable({ state, palette }: { state: DeckState; palette: SleevePalette }) {
  const grooves = Array.from({ length: 22 }, (_, i) => 19 + i * 1.35)
  return (
    <div className={`turntable is-${state}`} aria-hidden="true">
      <div className="platter">
        <svg className="record" viewBox="0 0 100 100">
          <defs>
            <radialGradient id="vinyl" cx=".5" cy=".5" r=".5">
              <stop offset=".3" stopColor="#1f1416" />
              <stop offset="1" stopColor="#0a0506" />
            </radialGradient>
          </defs>
          <circle cx="50" cy="50" r="49" fill="url(#vinyl)" />
          <g fill="none" stroke="#f7ede4" strokeWidth=".18">
            {grooves.map((r, i) => (
              <circle key={r} cx="50" cy="50" r={r} strokeOpacity={i % 4 === 0 ? 0.2 : 0.08} />
            ))}
          </g>
          <circle cx="50" cy="50" r="17" fill={palette.fg} className="record-label" />
          <circle cx="50" cy="50" r="14.6" fill="none" stroke={palette.bg} strokeOpacity=".35" strokeWidth=".35" />
          <g transform="translate(40.6 39.8) scale(.3)">
            <BeamedNotes fill={palette.bg} />
          </g>
          <circle cx="50" cy="50" r="1.1" fill="#0a0506" />
        </svg>
        {/* light sheen stays still while the record turns beneath it */}
        <div className="record-sheen" />
      </div>
      <svg className="tonearm" viewBox="0 0 40 120">
        <circle cx="28" cy="12" r="9" fill="#2a1b1f" stroke="#4a3236" />
        <circle cx="28" cy="12" r="3.2" fill="#a8948e" />
        <path d="M28 12 L28 82 L16 102" fill="none" stroke="#c9b6ae" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        <rect x="9" y="99" width="11" height="8" rx="1.6" fill="#c9b6ae" transform="rotate(32 14.5 103)" />
      </svg>
    </div>
  )
}
