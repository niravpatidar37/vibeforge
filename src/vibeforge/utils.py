"""Shared utilities used across agents."""

from __future__ import annotations

import json
import logging
import os
import re
from math import ceil
from functools import lru_cache
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, TypeVar

import requests
from langsmith import traceable

logger = logging.getLogger(__name__)

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from langchain_groq import ChatGroq
    from .models import Playlist

_M = TypeVar("_M", bound=BaseModel)

DEFAULT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_CONTEXT_LIMIT = 8192
DEFAULT_REQUESTED_OUTPUT = 1800
HF_REQUESTED_OUTPUT = 1200
HF_MODEL_PREFIX = "hf:"
HF_FAST_MODEL = "hf:meta-llama/Llama-3.1-8B-Instruct"
AVAILABLE_HF_MODELS = [
    "hf:Qwen/Qwen2.5-72B-Instruct",
    "hf:meta-llama/Llama-3.1-8B-Instruct",
]
AVAILABLE_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    *AVAILABLE_HF_MODELS,
]

PLAYLIST_CURATOR_RULES = """\
- Exactly 10 tracks that genuinely fit the mood.
- Quality mix (like Spotify/YouTube algorithm): 2 well-known hits the user probably loves, 3 cult classics or critically acclaimed deep cuts, 3 fresh discoveries the user likely hasn't heard, 2 wildcard picks from other languages or genres that still fit the vibe.
- Prioritise the user's "loved tracks" — match their energy, genre, and era first. Include 1-2 of them if they fit the mood.
- Include 1-2 "session favorites" if they fit the mood and aren't recently heard.
- Skip every track listed under "recently heard" and "never play again" — no exceptions.
- Genre diversity: no single genre should exceed 40% of the playlist (max 4 out of 10 tracks). Actively mix genres.
- Artist diversity: no artist appears more than twice.
- Support all languages and genres (Bollywood, K-pop, Latin, Afrobeats, jazz, classical, etc.)."""

_PLAYLIST_SCHEMA_DICT = {
    "name": "string",
    "mood_summary": "string",
    "vibe_tags": ["string"],
    "energy_level": "low|medium|high",
    "genres": ["string"],
    "tracks": [{
        "title": "string",
        "artist": "string",
        "genre": "string",
        "bpm": 120,
        "spotify_search_url": "",
        "youtube_search_url": "",
    }],
}
PLAYLIST_JSON_SCHEMA = json.dumps(_PLAYLIST_SCHEMA_DICT, indent=2)

MOOD_ANALYST_PROMPT = """You are a music psychologist and emotion expert.
Analyse the user's mood/activity input and return ONLY valid JSON — no markdown, no extra text:
{
  "primary_emotion": "string",
  "secondary_emotions": ["string"],
  "energy_level": "low|medium|high",
  "bpm_range": "60-80",
  "recommended_genres": ["string"],
  "avoid_genres": ["string"],
  "time_of_day_context": "string",
  "activity_context": "string",
  "musical_key_feel": "major|minor|modal",
  "occasion": "null or a single word/phrase naming the specific life event (birthday, wedding, graduation, etc.) if one is clearly present — otherwise null"
}"""

MUSIC_CURATOR_PROMPT = (
    "You are a world-class DJ and music curator with encyclopaedic knowledge of songs across all genres, eras, and languages.\n"
    "Given a mood analysis (and optional critic feedback), curate a 10-track playlist.\n"
    "Return ONLY valid JSON — no markdown, no extra text:\n"
    + PLAYLIST_JSON_SCHEMA + "\n"
    "Rules:\n"
    + PLAYLIST_CURATOR_RULES + "\n"
    "- Let weather, season, and day of week shape the energy and texture.\n"
    "- BPM values must fall within the bpm_range from the mood analysis."
)

OCCASION_NOTE_TEMPLATE = (
    "\n\nOCCASION DETECTED: {occasion}\n"
    "At least 2 of your 10 tracks MUST be songs that are culturally synonymous with this occasion — "
    "chosen because their title, lyrics, or widespread real-world use at such events makes them instantly "
    "recognisable as belonging to it, not merely because their energy fits."
)


@lru_cache(maxsize=16)
def get_cached_llm(model: str, temperature: float = 0.8) -> Any:
    """Return a cached provider client shared across all pipeline modes."""
    if model.startswith(HF_MODEL_PREFIX):
        return HuggingFaceChatModel(model.removeprefix(HF_MODEL_PREFIX), temperature)
    from langchain_groq import ChatGroq
    return ChatGroq(model=model, temperature=temperature)


def get_role_llm(model: str, role: str, temperature: float) -> Any:
    """Use a faster HF model for analysis roles while retaining the chosen curator."""
    if model.startswith(HF_MODEL_PREFIX) and role in {"analyst", "critic"}:
        return get_cached_llm(HF_FAST_MODEL, temperature)
    return get_cached_llm(model, temperature)


class HuggingFaceChatModel:
    """Small OpenAI-compatible client for Hugging Face Inference Providers."""

    endpoint = "https://router.huggingface.co/v1/chat/completions"

    def __init__(self, model: str, temperature: float) -> None:
        self.model = model
        self.temperature = temperature
        self.requested_output = HF_REQUESTED_OUTPUT

    @traceable(name="huggingface.chat", run_type="llm")
    def invoke(self, messages: list[Any]) -> Any:
        token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
        if not token:
            raise RuntimeError("HF_TOKEN is required when using a Hugging Face model")
        payload = {
            "model": self.model,
            "messages": [
                {"role": _message_role(message), "content": str(message.content)}
                for message in messages
            ],
            "temperature": self.temperature,
            "max_tokens": HF_REQUESTED_OUTPUT,
            "stream": False,
        }
        try:
            response = requests.post(
                os.getenv("HF_API_URL", self.endpoint),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
                timeout=90,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return SimpleNamespace(content=content)
        except requests.HTTPError as exc:
            detail = exc.response.text[:500] if exc.response is not None else ""
            logger.warning("Hugging Face rejected %s (%s): %s", self.model, exc.response.status_code if exc.response is not None else "unknown", detail)
            raise RuntimeError(f"Hugging Face inference failed for {self.model}") from exc
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Hugging Face inference failed for {self.model}") from exc


def _message_role(message: Any) -> str:
    role = getattr(message, "type", "user")
    return {"human": "user", "ai": "assistant"}.get(role, role)


def _format_json_error(exc: json.JSONDecodeError) -> str:
    return f"Response was not valid JSON at position {exc.pos}: {exc.msg}"


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors()[:3]:
        loc = ".".join(str(p) for p in err.get("loc", []))
        msg = err.get("msg", "invalid value")
        parts.append(f"{loc}: {msg}" if loc else msg)
    remaining = len(exc.errors()) - len(parts)
    if remaining > 0:
        parts.append(f"... and {remaining} more error(s)")
    return "; ".join(parts)


def count_tokens(tokenizer: Any, text: str) -> int:
    """Count tokens with a model tokenizer, or conservatively estimate them."""
    if tokenizer is not None:
        return len(tokenizer.encode(text, add_special_tokens=False))
    return max(1, ceil(len(text) / 4))


def count_message_tokens(messages: list[Any], tokenizer: Any = None) -> int:
    """Count the text sent to a chat model, including a small message overhead."""
    return sum(count_tokens(tokenizer, str(message.content)) + 4 for message in messages)


def ensure_context_budget(
    messages: list[Any],
    tokenizer: Any = None,
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
    requested_output: int = DEFAULT_REQUESTED_OUTPUT,
) -> None:
    """Reject prompts that leave too little room for the structured response."""
    available_input = context_limit - requested_output
    input_tokens = count_message_tokens(messages, tokenizer)
    if input_tokens > available_input:
        raise ValueError(
            f"Prompt is too large for this model ({input_tokens} input tokens; "
            f"maximum {available_input} with {requested_output} reserved for output)"
        )


def invoke_with_retry(llm: Any, messages: list[Any], model_class: type[_M], label: str, max_attempts: int = 3) -> _M:
    """Invoke LLM, extract JSON from the response, validate with Pydantic — retry on failure."""
    from langchain_core.messages import HumanMessage

    for attempt in range(max_attempts):
        ensure_context_budget(
            messages,
            requested_output=getattr(llm, "requested_output", DEFAULT_REQUESTED_OUTPUT),
        )
        resp = llm.invoke(messages)
        raw = strip_fences(str(resp.content))
        try:
            return model_class(**json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            summary = _format_json_error(exc) if isinstance(exc, json.JSONDecodeError) else _format_validation_error(exc)
            if attempt == max_attempts - 1:
                raise RuntimeError(f"{label} returned invalid JSON after {max_attempts} attempts: {summary}") from exc
            messages = [*messages, HumanMessage(content=f"Your response had errors: {summary}. Return valid JSON only.")]
    raise AssertionError("unreachable")


def clamp_bpm(playlist: Playlist, bpm_range: str) -> None:
    """Clamp track BPMs into the analyst's recommended range, logging violations."""
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", bpm_range.strip())
    if not match:
        return
    lo, hi = int(match.group(1)), int(match.group(2))
    for track in playlist.tracks:
        if track.bpm is not None and not (lo <= track.bpm <= hi):
            logger.warning("Track '%s' BPM %d outside %s — clamping", track.title, track.bpm, bpm_range)
            track.bpm = max(lo, min(hi, track.bpm))


def strip_fences(raw: str) -> str:
    """Extract JSON from LLM output — handles fenced blocks and bare unfenced JSON."""
    raw = raw.strip()
    match = re.search(r"```[^\n]*\n(.*?)```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: extract the outermost {...} block when the model skips fences
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        return raw[start:end + 1]
    return raw
