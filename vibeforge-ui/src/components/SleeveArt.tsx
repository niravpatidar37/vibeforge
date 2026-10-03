import type { SleeveDesign } from '../lib/sleeve'

/**
 * Generated album artwork. Pure geometry from a deterministic design, so the same
 * playlist always gets the same sleeve. Text is rendered by the caller as HTML
 * (React-escaped), never injected into the SVG markup.
 */
export default function SleeveArt({ design, className }: { design: SleeveDesign; className?: string }) {
  const { palette, sunX, sunY, rings, rays, seed } = design
  const cx = sunX * 100
  const cy = sunY * 100
  const sunR = 17
  const horizon = Math.min(92, cy + 6)
  return (
    <svg className={className} viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <rect width="100" height="100" fill={palette.bg} />
      {/* rings ripple out from the disc, like sound */}
      <g fill="none" stroke={palette.fg} strokeWidth=".45">
        {Array.from({ length: rings }, (_, i) => (
          <circle key={i} cx={cx} cy={cy} r={sunR + 5 + i * 5.5} strokeOpacity={0.55 - i * (0.45 / rings)} />
        ))}
      </g>
      {rays > 0 && (
        <g stroke={palette.accent} strokeWidth=".6" strokeLinecap="round" strokeOpacity=".5">
          {Array.from({ length: rays }, (_, i) => {
            const a = (i / rays) * Math.PI * 2 + (seed % 7) * 0.1
            return (
              <line key={i} x1={cx + Math.cos(a) * (sunR + 3)} y1={cy + Math.sin(a) * (sunR + 3)}
                x2={cx + Math.cos(a) * (sunR + 10 + (i % 3) * 4)} y2={cy + Math.sin(a) * (sunR + 10 + (i % 3) * 4)} />
            )
          })}
        </g>
      )}
      <circle cx={cx} cy={cy} r={sunR} fill={palette.fg} />
      <circle cx={cx - sunR * 0.3} cy={cy - sunR * 0.3} r={sunR * 0.55} fill={palette.accent} fillOpacity=".28" />
      {/* horizon bands: low-energy moods set behind them like a sunset */}
      <rect y={horizon} width="100" height={100 - horizon} fill={palette.bg} />
      {Array.from({ length: 4 }, (_, i) => (
        <rect key={i} y={horizon + 1.5 + i * 2.6} width="100" height={0.7 + i * 0.25} fill={palette.fg} fillOpacity={0.5 - i * 0.1} />
      ))}
    </svg>
  )
}
