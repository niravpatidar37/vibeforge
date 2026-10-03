"""Single LangChain agent that generates a mood-based playlist."""

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage

from .models import Playlist, Track
from .context import build_context_string
from .memory import get_preference_context, save_session
from .spotify import enrich_tracks_with_spotify
from .utils import PLAYLIST_JSON_SCHEMA, PLAYLIST_CURATOR_RULES, DEFAULT_MODEL, get_cached_llm, invoke_with_retry

SYSTEM_PROMPT = (
    "You are VibeForge, an expert music curator AI trained on decades of listening data.\n"
    "Your job is to craft a playlist that feels handpicked — like a friend who knows your taste perfectly.\n\n"
    "Rules:\n"
    "- Return ONLY valid JSON matching the Playlist schema — no markdown, no extra text.\n"
    + PLAYLIST_CURATOR_RULES + "\n"
    "- Let weather, season, and day of week shape the energy "
    "(e.g. rainy winter evening → melancholy indie; sunny weekend morning → feel-good pop).\n"
    "- If a seed track is provided, use it as a vibe anchor — match its era, energy, and feel.\n"
    "- Set spotify_search_url and youtube_search_url to empty strings — they will be filled automatically.\n"
    "- bpm should be an integer reflecting the track's approximate tempo.\n\n"
    "Playlist JSON schema:\n"
    + PLAYLIST_JSON_SCHEMA
)


def _check_genre_diversity(playlist: Playlist) -> str | None:
    """Return a correction message if any genre dominates more than 40% of tracks."""
    from collections import Counter
    genre_counts = Counter(t.genre.lower() for t in playlist.tracks)
    dominant = [(g, c) for g, c in genre_counts.items() if c > len(playlist.tracks) * 0.4]
    if dominant:
        over = ", ".join(f'"{g}" ({c} tracks)' for g, c in dominant)
        return (
            f"Genre diversity violation: {over} exceed 40% of the playlist. "
            "Replace some tracks with different genres while keeping the mood. Return corrected JSON only."
        )
    return None


def generate_playlist(
    mood_input: str,
    context_extra: str = "",
    model: str = DEFAULT_MODEL,
    spotify_enrich: bool = True,
    seed: str = "",
) -> Playlist:
    """Generate a Playlist from a natural-language mood description."""
    llm = get_cached_llm(model)

    context = build_context_string(context_extra, seed=seed)
    preferences = get_preference_context()

    user_content_parts = [
        f"Mood / activity: {mood_input}",
        f"Context:\n{context}",
    ]
    if preferences:
        user_content_parts.append(f"Memory context (follow strictly):\n{preferences}")

    messages: list[BaseMessage] = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content="\n\n".join(user_content_parts)),
    ]

    playlist = invoke_with_retry(llm, messages, Playlist, "VibeForge")

    correction = _check_genre_diversity(playlist)
    if correction:
        messages = [*messages, HumanMessage(content=correction)]
        playlist = invoke_with_retry(llm, messages, Playlist, "VibeForge (genre correction)")

    if spotify_enrich:
        enriched = enrich_tracks_with_spotify([t.model_dump() for t in playlist.tracks])
        playlist.tracks = [Track(**t) for t in enriched]

    save_session(mood_input, playlist.model_dump())
    return playlist
