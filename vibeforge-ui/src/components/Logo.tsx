import { useId } from 'react'

/** The VibeForge mark: a guitar pick (its point is the V) with beamed eighth notes. */
export function PickMark({ size = 32, title }: { size?: number; title?: string }) {
  const gid = `pick-${useId().replace(/:/g, '')}`
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      className="pick-mark"
    >
      <defs>
        <linearGradient id={gid} x1="0.15" y1="0" x2="0.85" y2="1">
          <stop offset="0" stopColor="#ffb05c" />
          <stop offset=".5" stopColor="#ff4f6d" />
          <stop offset="1" stopColor="#b3174f" />
        </linearGradient>
      </defs>
      <path d="M32 59 C27 54 9 37 8 23 C7 11 19 5.5 32 5.5 C45 5.5 57 11 56 23 C55 37 37 54 32 59Z" fill={`url(#${gid})`} />
      <path d="M15 16 Q22 9 33 8.5 L33 11.5 Q23 12.5 17 18Z" fill="#f7ede4" fillOpacity=".28" />
      <BeamedNotes />
    </svg>
  )
}

/** Beamed eighth notes in the mark's 64-unit coordinate space. */
export function BeamedNotes({ fill = '#140c0e' }: { fill?: string }) {
  return (
    <g fill={fill}>
      <ellipse cx="23.5" cy="37" rx="4.97" ry="3.59" transform="rotate(-24 23.5 37)" />
      <ellipse cx="39.14" cy="33.32" rx="4.97" ry="3.59" transform="rotate(-24 39.14 33.32)" />
      <rect x="25.52" y="16.76" width="2.21" height="19.32" />
      <rect x="41.16" y="13.08" width="2.21" height="19.32" />
      <path d="M25.52 16.76 L43.37 13.08 L43.37 17.68 L25.52 21.36Z" />
    </g>
  )
}

export function Wordmark() {
  return (
    <span className="wordmark">
      Vibe<em>Forge</em>
    </span>
  )
}
