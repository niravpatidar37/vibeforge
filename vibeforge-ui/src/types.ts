export interface Track {
  title: string
  artist: string
  genre: string
  bpm: number | null
  spotify_search_url: string
  youtube_search_url: string
}

export interface Playlist {
  name: string
  mood_summary: string
  vibe_tags: string[]
  energy_level: 'low' | 'medium' | 'high'
  genres: string[]
  tracks: Track[]
}

export type Mode = 'fast' | 'deep' | 'agentic'

export interface ProgressEvent {
  node: string
  /** present when node === 'error' */
  message?: string
  data?: {
    emotion?: string
    energy?: string
    bpm_range?: string
    occasion?: string | null
    score?: number
    feedback?: string
    attempt?: number
    // playlist fields when node === 'finalise'
    name?: string
    tracks?: Track[]
    [key: string]: unknown
  }
}
