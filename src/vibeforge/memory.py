"""Simple file-based session memory for learning user preferences."""

import json
import logging
import os
import threading
from pathlib import Path
from datetime import datetime
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)

MAX_FEEDBACK_ENTRIES = 200
MAX_PREFERENCE_CHARS = 6000
_memory_lock = threading.RLock()


def _memory_file() -> Path:
    """Resolve the memory file path on each call so VIBEFORGE_DATA_DIR overrides work at any time."""
    custom = os.getenv("VIBEFORGE_DATA_DIR")
    base = Path(custom) if custom else Path.home() / ".vibeforge"
    base.mkdir(parents=True, exist_ok=True)
    return base / "memory.json"


def _load() -> dict:
    path = _memory_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        backup = path.with_suffix(".json.bak")
        try:
            backup.unlink(missing_ok=True)  # always replace stale backup
            path.rename(backup)
            logger.warning("Corrupt memory file backed up to %s", backup)
        except OSError as exc:
            logger.warning("Could not back up corrupt memory file %s: %s", path, exc)
        return {}


def _save(data: dict) -> None:
    path = _memory_file()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _compact_sections(sections: list[str], max_chars: int = MAX_PREFERENCE_CHARS) -> str:
    """Keep high-priority sections first and trim low-priority history."""
    selected: list[str] = []
    used = 0
    for section in sections:
        separator = 2 if selected else 0
        remaining = max_chars - used - separator
        if remaining <= 0:
            break
        selected.append(section[:remaining])
        used += separator + min(len(section), remaining)
    return "\n\n".join(selected)


def get_loved_track_keys() -> frozenset[str]:
    """Return lowercase "title by artist" keys for tracks the user has marked loved."""
    with _memory_lock:
        data = _load()
    loved: dict[str, int] = data.get("feedback", {}).get("loved", {})
    return frozenset(key.lower() for key in loved)


def get_preference_context() -> str:
    """Return a blended memory context: favorites to revisit + recent tracks to skip."""
    with _memory_lock:
        data = _load()
    sessions = data.get("sessions", [])
    feedback = data.get("feedback", {})
    loved_tracks: dict[str, int] = feedback.get("loved", {})
    disliked_tracks: set[str] = set(feedback.get("disliked", {}).keys())

    sections: list[str] = []

    # Explicit loved tracks (highest priority — always try to match their vibe)
    if loved_tracks:
        top_loved = sorted(loved_tracks, key=loved_tracks.get, reverse=True)[:8]  # type: ignore[arg-type]
        sections.append(
            "User's all-time loved tracks (prioritise their vibe, energy, and genre in your picks):\n"
            + "\n".join(f"  - {t}" for t in top_loved)
        )

    # Session-based favorites: appeared in 2+ separate sessions
    track_counts: dict[str, int] = {}
    for s in sessions:
        for t in s.get("tracks", []):
            title, artist = t.get("title"), t.get("artist")
            if not title or not artist:
                continue
            key = f"{title} by {artist}"
            track_counts[key] = track_counts.get(key, 0) + 1

    session_favorites = [
        t for t, c in sorted(track_counts.items(), key=lambda x: -x[1])
        if c >= 2 and t not in disliked_tracks and t not in loved_tracks
    ]

    # Recently heard (last 2 sessions): skip unless they're session favorites or loved
    recently_heard: set[str] = set()
    for s in sessions[-2:]:
        for t in s.get("tracks", []):
            title, artist = t.get("title"), t.get("artist")
            if not title or not artist:
                continue
            key = f"{title} by {artist}"
            if key not in session_favorites and key not in loved_tracks:
                recently_heard.add(key)

    # Genre preferences across all sessions
    liked_genres: dict[str, int] = {}
    for s in sessions:
        for g in s.get("genres", []):
            liked_genres[g] = liked_genres.get(g, 0) + 1
    top_genres = sorted(liked_genres, key=liked_genres.get, reverse=True)[:5]  # type: ignore[arg-type]

    if top_genres:
        sections.append(f"Preferred genres: {', '.join(top_genres)}")
    if session_favorites:
        sections.append(
            "Session favorites (include 1-2 of these if they fit the mood):\n"
            + "\n".join(f"  - {t}" for t in session_favorites[:8])
        )
    if recently_heard:
        sections.append(
            "Recently heard — skip these to keep it fresh:\n"
            + "\n".join(f"  - {t}" for t in list(recently_heard)[:20])
        )
    if disliked_tracks:
        sections.append(
            "Tracks to NEVER include (user disliked these):\n"
            + "\n".join(f"  - {t}" for t in list(disliked_tracks)[:20])
        )
    return _compact_sections(sections)


def save_feedback(loved: Sequence[Mapping[str, Any]], disliked: Sequence[Mapping[str, Any]]) -> None:
    """Persist explicit per-track feedback from the user."""
    with _memory_lock:
        data = _load()
        fb = data.setdefault("feedback", {"loved": {}, "disliked": {}})
        for t in loved:
            key = f"{t['title']} by {t['artist']}"
            fb["loved"][key] = fb["loved"].get(key, 0) + 1
            fb["disliked"].pop(key, None)  # un-dislike if previously marked
        for t in disliked:
            key = f"{t['title']} by {t['artist']}"
            fb["disliked"][key] = fb["disliked"].get(key, 0) + 1
            fb["loved"].pop(key, None)  # un-love if previously marked
        for bucket in ("loved", "disliked"):
            if len(fb[bucket]) > MAX_FEEDBACK_ENTRIES:
                fb[bucket] = dict(
                    sorted(fb[bucket].items(), key=lambda kv: kv[1], reverse=True)[:MAX_FEEDBACK_ENTRIES]
                )
        _save(data)


def save_session(mood_input: str, playlist: dict[str, Any]) -> None:
    with _memory_lock:
        data = _load()
        if "sessions" not in data:
            data["sessions"] = []
        data["sessions"].append({
            "timestamp": datetime.now().isoformat(),
            "mood_input": mood_input,
            "playlist_name": playlist.get("name", ""),
            "genres": playlist.get("genres", []),
            "tracks": [{"title": t["title"], "artist": t["artist"]} for t in playlist.get("tracks", [])],
        })
        # Keep last 20 sessions
        data["sessions"] = data["sessions"][-20:]
        _save(data)
