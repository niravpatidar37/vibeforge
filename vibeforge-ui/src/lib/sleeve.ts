import type { Playlist } from '../types'

export interface SleevePalette {
  name: string
  bg: string
  fg: string
  accent: string
  text: string
}

/** Curated duotones. Every playlist gets one, picked deterministically from its name. */
const PALETTES: SleevePalette[] = [
  { name: 'ember',     bg: '#2a0f16', fg: '#ff4f6d', accent: '#ffb05c', text: '#f7ede4' },
  { name: 'plum dusk', bg: '#2b1328', fg: '#ff8a65', accent: '#ffd3a5', text: '#f7ede4' },
  { name: 'low tide',  bg: '#0f2a2c', fg: '#7fd1c3', accent: '#f7ede4', text: '#f7ede4' },
  { name: 'high sun',  bg: '#ffb05c', fg: '#b3174f', accent: '#140c0e', text: '#140c0e' },
  { name: 'love note', bg: '#f7ede4', fg: '#b3174f', accent: '#ff4f6d', text: '#140c0e' },
  { name: 'gold room', bg: '#1b1a17', fg: '#e8c07d', accent: '#ff4f6d', text: '#f7ede4' },
]

export const IDLE_PALETTE = PALETTES[0]

/** FNV-1a: tiny, stable string hash. Not for security, just for picking artwork. */
function hash(s: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

export interface SleeveDesign {
  palette: SleevePalette
  /** 0..1 horizontal position of the sun/disc */
  sunX: number
  /** 0..1 vertical position: low energy sets low like a sunset, high energy rides high */
  sunY: number
  rings: number
  rays: number
  seed: number
}

export function sleeveFor(playlist: Pick<Playlist, 'name' | 'mood_summary' | 'energy_level'>): SleeveDesign {
  const seed = hash(`${playlist.name}|${playlist.mood_summary}`)
  const palette = PALETTES[seed % PALETTES.length]
  const jitter = ((seed >>> 8) % 100) / 100
  const energy = playlist.energy_level
  return {
    palette,
    seed,
    sunX: 0.3 + jitter * 0.4,
    sunY: energy === 'low' ? 0.74 : energy === 'medium' ? 0.5 : 0.34,
    rings: energy === 'low' ? 3 : energy === 'medium' ? 6 : 9,
    rays: energy === 'high' ? 18 : 0,
  }
}
