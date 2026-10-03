"""Deterministic playlist quality checks shared by runtime and evaluations."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .models import MoodAnalysis, Playlist


def validate_playlist(playlist: Playlist, mood_analysis: MoodAnalysis | None = None) -> list[str]:
    """Return objective rule violations without making another model call."""
    issues: list[str] = []
    if len(playlist.tracks) != 10:
        issues.append("Playlist must contain exactly 10 tracks")
    artist_counts = Counter(track.artist.strip().lower() for track in playlist.tracks)
    if any(count > 2 for count in artist_counts.values()):
        issues.append("Artist diversity violation: no artist may appear more than twice")
    track_keys = [f"{track.title.strip().lower()} by {track.artist.strip().lower()}" for track in playlist.tracks]
    if len(track_keys) != len(set(track_keys)):
        issues.append("Duplicate track violation: the same title and artist may not appear more than once")
    genre_counts = Counter(track.genre.strip().lower() for track in playlist.tracks)
    if any(count > 4 for count in genre_counts.values()):
        issues.append("Genre diversity violation: no genre may exceed four tracks")
    if mood_analysis:
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", mood_analysis.bpm_range.strip())
        if match:
            low, high = int(match.group(1)), int(match.group(2))
            if any(track.bpm is not None and not low <= track.bpm <= high for track in playlist.tracks):
                issues.append(f"BPM violation: tracks must stay within {mood_analysis.bpm_range}")
    return issues


def repair_playlist(playlist: Playlist, loved_keys: frozenset[str] = frozenset()) -> None:
    """Drop duplicate tracks and trim artist/genre overflow in place, mirroring clamp_bpm.

    When a cap forces a choice between tracks, tracks the user has marked "loved"
    (see memory.get_loved_track_keys) are kept over ones they haven't rated.
    """
    def track_key(track: Any) -> str:
        return f"{track.title.strip().lower()} by {track.artist.strip().lower()}"

    evaluation_order = sorted(
        range(len(playlist.tracks)),
        key=lambda i: track_key(playlist.tracks[i]) not in loved_keys,
    )

    seen_keys: set[str] = set()
    artist_counts: Counter[str] = Counter()
    genre_counts: Counter[str] = Counter()
    keep_indices: set[int] = set()
    for i in evaluation_order:
        track = playlist.tracks[i]
        key = track_key(track)
        artist = track.artist.strip().lower()
        genre = track.genre.strip().lower()
        if key in seen_keys or artist_counts[artist] >= 2 or genre_counts[genre] >= 4:
            continue
        seen_keys.add(key)
        artist_counts[artist] += 1
        genre_counts[genre] += 1
        keep_indices.add(i)
    if len(keep_indices) != len(playlist.tracks):
        playlist.tracks = [t for i, t in enumerate(playlist.tracks) if i in keep_indices]


def playlist_rule_evaluator(inputs: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    """LangSmith evaluator for objective playlist constraints."""
    raw_playlist = outputs.get("playlist", outputs)
    playlist = raw_playlist if isinstance(raw_playlist, Playlist) else Playlist.model_validate(raw_playlist)
    issues = validate_playlist(playlist)
    return {"key": "playlist_rules", "score": float(not issues), "comment": "; ".join(issues)}
