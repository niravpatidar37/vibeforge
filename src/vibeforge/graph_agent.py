"""LangGraph agentic pipeline: Mood Analyst → Curator → Critic → (refine?) → Finalise.

Four-node state machine with a self-correcting loop:
  analyse_mood → curate_playlist → critique_playlist
                      ↑                   │ score < 7 and attempts < 2
                      └─── refine ────────┘
                                          │ score >= 7 or max attempts reached
                                          ↓
                                       finalise → END
"""

from __future__ import annotations

import logging
from typing import Any, Generator, Iterable, TypedDict, cast

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .models import MoodAnalysis, Playlist, Track
from .context import build_context_string
from .memory import get_loved_track_keys, get_preference_context, save_session
from .quality import validate_playlist as _validate_playlist, repair_playlist as _repair_playlist
from .spotify import enrich_tracks_with_spotify
from .utils import (
    DEFAULT_MODEL, MOOD_ANALYST_PROMPT, MUSIC_CURATOR_PROMPT, OCCASION_NOTE_TEMPLATE,
    get_cached_llm, get_role_llm, invoke_with_retry, clamp_bpm,
)

logger = logging.getLogger(__name__)

ACCEPT_SCORE = 7
MAX_REFINEMENTS = 2


# ── Models ────────────────────────────────────────────────────────────────────

class PlaylistCritique(BaseModel):
    score: int = Field(ge=1, le=10, description="Overall quality score 1–10")
    issues: list[str] = Field(description="Specific problems found in the playlist")
    feedback: str = Field(description="Actionable instructions for the curator to fix the issues")


# ── Shared state ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    mood_input: str
    context_extra: str
    seed: str
    model: str
    spotify_enrich: bool
    mood_analysis: MoodAnalysis | None
    playlist: Playlist | None
    critique: PlaylistCritique | None
    refinement_attempts: int


# ── Prompts ───────────────────────────────────────────────────────────────────

_CRITIC_PROMPT = """You are a music playlist quality critic. Evaluate the playlist against these criteria:
1. Genre diversity — no single genre > 40% of tracks (max 4/10)
2. Artist diversity — no artist appears more than twice
3. Mood coherence — tracks genuinely fit the stated mood and energy level
4. Discovery balance — mix of well-known hits, deep cuts, and fresh finds
5. Track authenticity — all tracks are real, well-known recordings

Return ONLY valid JSON — no markdown, no extra text:
{
  "score": 8,
  "issues": ["specific issue 1", "specific issue 2"],
  "feedback": "Specific actionable instructions for the curator to improve the playlist"
}

Score 8–10: excellent, accept as-is.
Score 5–7: decent but fixable — provide clear fix instructions.
Score 1–4: significant problems — be specific about what must change."""


# ── Node functions ────────────────────────────────────────────────────────────

def _analyse_mood(state: AgentState) -> AgentState:
    llm = get_role_llm(state["model"], "analyst", 0.7)
    context = build_context_string(state["context_extra"], seed=state["seed"])
    preferences = get_preference_context()
    user_msg = "\n\n".join(filter(None, [
        f"Mood / activity: {state['mood_input']}",
        f"Context:\n{context}",
        f"Memory context (follow strictly):\n{preferences}" if preferences else "",
    ]))
    mood_analysis = invoke_with_retry(
        llm,
        [SystemMessage(content=MOOD_ANALYST_PROMPT), HumanMessage(content=user_msg)],
        MoodAnalysis,
        "Mood Analyst",
    )
    logger.info("Mood analysis: %s | BPM %s | %s", mood_analysis.primary_emotion, mood_analysis.bpm_range, mood_analysis.energy_level)
    return {**state, "mood_analysis": mood_analysis}


def _curate_playlist(state: AgentState) -> AgentState:
    llm = get_cached_llm(state["model"], 0.8)
    mood_analysis = state["mood_analysis"]
    assert mood_analysis is not None

    curator_content = f"Mood analysis:\n{mood_analysis.model_dump_json(indent=2)}"
    if mood_analysis.occasion:
        curator_content += OCCASION_NOTE_TEMPLATE.format(occasion=mood_analysis.occasion.upper())
    critique = state.get("critique")
    if critique and state["refinement_attempts"] > 0:
        curator_content += (
            f"\n\nCritic review (score {critique.score}/10 — needs improvement):\n"
            f"Issues: {'; '.join(critique.issues)}\n"
            f"Feedback: {critique.feedback}\n"
            "Please address ALL issues above in your revised playlist."
        )

    playlist = invoke_with_retry(
        llm,
        [SystemMessage(content=MUSIC_CURATOR_PROMPT), HumanMessage(content=curator_content)],
        Playlist,
        "Music Curator",
    )
    clamp_bpm(playlist, mood_analysis.bpm_range)
    logger.info("Curator generated '%s' (attempt %d)", playlist.name, state["refinement_attempts"] + 1)
    return {**state, "playlist": playlist}


def _critique_playlist(state: AgentState) -> AgentState:
    playlist = state["playlist"]
    assert playlist is not None

    deterministic_issues = _validate_playlist(playlist, state["mood_analysis"])
    if deterministic_issues:
        critique = PlaylistCritique(
            score=5,
            issues=deterministic_issues,
            feedback="Fix every deterministic playlist rule violation before the next attempt.",
        )
        logger.info("Deterministic playlist validation found %d issue(s)", len(deterministic_issues))
        return {**state, "critique": critique}

    llm = get_role_llm(state["model"], "critic", 0.3)
    critique = invoke_with_retry(
        llm,
        [
            SystemMessage(content=_CRITIC_PROMPT),
            HumanMessage(content=f"Mood: {state['mood_input']}\n\nPlaylist:\n{playlist.model_dump_json(indent=2)}"),
        ],
        PlaylistCritique,
        "Critic",
    )
    logger.info("Critic score: %d/10 — %s", critique.score, critique.feedback[:100])
    return {**state, "critique": critique}


def _route_after_critique(state: AgentState) -> str:
    critique = state.get("critique")
    if critique and critique.score < ACCEPT_SCORE and state["refinement_attempts"] < MAX_REFINEMENTS:
        logger.info("Score %d < %d — refining (attempt %d/%d)", critique.score, ACCEPT_SCORE, state["refinement_attempts"] + 1, MAX_REFINEMENTS)
        return "refine"
    return "finalise"


def _increment_attempts(state: AgentState) -> AgentState:
    return {**state, "refinement_attempts": state["refinement_attempts"] + 1}


def _finalise(state: AgentState) -> AgentState:
    playlist = state["playlist"]
    assert playlist is not None
    if _validate_playlist(playlist, state["mood_analysis"]):
        _repair_playlist(playlist, loved_keys=get_loved_track_keys())
    hard_issues = _validate_playlist(playlist, state["mood_analysis"])
    # Dropping duplicate/overflow tracks always trips the "exactly 10" rule — that's
    # an expected side-effect of repair, not a real failure, so only hard-fail on
    # anything the repair couldn't have caused.
    if len(playlist.tracks) < 10:
        hard_issues = [i for i in hard_issues if "exactly 10 tracks" not in i]
    if hard_issues:
        raise RuntimeError(f"Playlist still violates hard rules after refinement: {'; '.join(hard_issues)}")
    if len(playlist.tracks) < 10:
        logger.warning("Finalising playlist with %d tracks after repairing rule violations", len(playlist.tracks))
    if state["spotify_enrich"]:
        enriched = enrich_tracks_with_spotify([t.model_dump() for t in playlist.tracks])
        playlist.tracks = [Track(**t) for t in enriched]
    save_session(state["mood_input"], playlist.model_dump())
    critique = state.get("critique")
    if critique:
        logger.info("Final playlist accepted at score %d/10", critique.score)
    return {**state, "playlist": playlist}


# ── Graph construction ────────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("analyse_mood", _analyse_mood)
    g.add_node("curate_playlist", _curate_playlist)
    g.add_node("critique_playlist", _critique_playlist)
    g.add_node("increment_attempts", _increment_attempts)
    g.add_node("finalise", _finalise)

    g.set_entry_point("analyse_mood")
    g.add_edge("analyse_mood", "curate_playlist")
    g.add_edge("curate_playlist", "critique_playlist")
    g.add_conditional_edges(
        "critique_playlist",
        _route_after_critique,
        {"refine": "increment_attempts", "finalise": "finalise"},
    )
    g.add_edge("increment_attempts", "curate_playlist")
    g.add_edge("finalise", END)
    return g.compile()


_COMPILED_GRAPH: Any = _build_graph()


# ── Public API ────────────────────────────────────────────────────────────────

def stream_playlist_with_graph(
    mood_input: str,
    context_extra: str = "",
    seed: str = "",
    model: str = DEFAULT_MODEL,
    spotify_enrich: bool = True,
) -> Generator[tuple[str, dict[str, Any]], None, None]:
    """Yield (node_name, full_state) after each graph node so callers can show live progress."""
    initial: AgentState = {
        "mood_input": mood_input,
        "context_extra": context_extra,
        "seed": seed,
        "model": model,
        "spotify_enrich": spotify_enrich,
        "mood_analysis": None,
        "playlist": None,
        "critique": None,
        "refinement_attempts": 0,
    }
    current: dict[str, Any] = {}
    stream = cast(Iterable[dict[str, Any]], _COMPILED_GRAPH.stream(initial, stream_mode="updates"))
    for chunk in stream:
        node_name: str = next(iter(chunk))
        current.update(chunk[node_name])
        yield node_name, current


def generate_playlist_with_graph(
    mood_input: str,
    context_extra: str = "",
    seed: str = "",
    model: str = DEFAULT_MODEL,
    spotify_enrich: bool = True,
) -> Playlist:
    """Run the full LangGraph agentic pipeline and return the final Playlist."""
    initial: AgentState = {
        "mood_input": mood_input,
        "context_extra": context_extra,
        "seed": seed,
        "model": model,
        "spotify_enrich": spotify_enrich,
        "mood_analysis": None,
        "playlist": None,
        "critique": None,
        "refinement_attempts": 0,
    }
    final = _COMPILED_GRAPH.invoke(initial)
    playlist = final["playlist"]
    if playlist is None:
        raise RuntimeError("LangGraph pipeline failed to produce a playlist.")
    return playlist
