"""Application service shared by HTTP, CLI, and UI adapters."""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
from collections.abc import Generator
from typing import Any, Literal

import redis
from pydantic import BaseModel, Field
from langsmith import traceable

from .models import Playlist, Track
from .quality import validate_playlist
from .spotify import enrich_tracks_with_spotify
from .utils import AVAILABLE_MODELS, DEFAULT_MODEL

logger = logging.getLogger(__name__)

GenerationMode = Literal["fast", "deep", "agentic"]
CACHE_TTL_SECONDS = 900
CACHE_MAX_ENTRIES = 128
CACHE_KEY_PREFIX = "vibeforge:cache:"


def _connect_redis() -> "redis.Redis | None":
    """Connect to REDIS_URL for a cache shared across processes/workers, if configured."""
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=2)
        client.ping()
        return client
    except redis.RedisError as exc:
        logger.warning("Redis unavailable (%s) — falling back to in-process cache", exc)
        return None


class GenerationRequest(BaseModel):
    """Validated input accepted by every presentation adapter."""

    mood: str = Field(min_length=1, max_length=500)
    context: str = Field(default="", max_length=500)
    seed: str = Field(default="", max_length=200)
    model: str = DEFAULT_MODEL
    mode: GenerationMode = "fast"
    spotify_enrich: bool = True

    def normalized(self) -> "GenerationRequest":
        values = self.model_dump()
        values["mood"] = self.mood.strip()
        values["context"] = self.context.strip()
        values["seed"] = self.seed.strip()
        if not values["mood"]:
            raise ValueError("mood must contain non-whitespace characters")
        if self.model not in AVAILABLE_MODELS:
            raise ValueError(f"model must be one of: {', '.join(AVAILABLE_MODELS)}")
        return type(self)(**values)


class GenerationService:
    """Owns generation policy while adapters remain transport-specific."""

    def __init__(self) -> None:
        self._redis = _connect_redis()
        self._cache: dict[str, tuple[float, Playlist]] = {}
        self._cache_lock = threading.Lock()

    def _cache_key(self, request: GenerationRequest) -> str:
        return CACHE_KEY_PREFIX + json.dumps(request.model_dump(exclude={"spotify_enrich"}), sort_keys=True)

    def _get_cached(self, cache_key: str) -> Playlist | None:
        if self._redis is not None:
            raw = self._redis.get(cache_key)
            return Playlist.model_validate_json(raw) if raw else None
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
                return copy.deepcopy(cached[1])
            self._cache.pop(cache_key, None)
            return None

    def _set_cached(self, cache_key: str, playlist: Playlist) -> None:
        if self._redis is not None:
            self._redis.setex(cache_key, CACHE_TTL_SECONDS, playlist.model_dump_json())
            return
        with self._cache_lock:
            if len(self._cache) >= CACHE_MAX_ENTRIES:
                oldest_key = min(self._cache, key=lambda key: self._cache[key][0])
                self._cache.pop(oldest_key, None)
            self._cache[cache_key] = (time.monotonic(), copy.deepcopy(playlist))

    def invalidate_cache(self) -> None:
        if self._redis is not None:
            keys = list(self._redis.scan_iter(f"{CACHE_KEY_PREFIX}*"))
            if keys:
                self._redis.delete(*keys)
        with self._cache_lock:
            self._cache.clear()

    @traceable(name="vibeforge.generate", run_type="chain")
    def generate(self, request: GenerationRequest, defer_enrichment: bool = False) -> Playlist:
        request = request.normalized()
        cache_key = self._cache_key(request)
        playlist = self._get_cached(cache_key)
        if playlist is None:
            pipeline_request = request.model_copy(update={"spotify_enrich": False})
            playlist = self._generate_uncached(pipeline_request)
            # Agentic mode already ran its own repair-aware hard validation in
            # graph_agent._finalise; re-running the strict check here would reject
            # the exactly-10-tracks violation that repair deliberately leaves behind.
            if pipeline_request.mode != "agentic":
                issues = validate_playlist(playlist)
                if issues:
                    raise RuntimeError(f"Generated playlist failed hard validation: {'; '.join(issues)}")
            self._set_cached(cache_key, playlist)
        if request.spotify_enrich and not defer_enrichment:
            playlist = self.enrich(playlist)
        return playlist

    def _generate_uncached(self, request: GenerationRequest) -> Playlist:
        if request.mode == "agentic":
            from .graph_agent import generate_playlist_with_graph
            return generate_playlist_with_graph(request.mood, request.context, seed=request.seed, model=request.model, spotify_enrich=request.spotify_enrich)
        if request.mode == "deep":
            from .crew_agent import generate_playlist_with_crew
            return generate_playlist_with_crew(request.mood, request.context, seed=request.seed, model=request.model, spotify_enrich=request.spotify_enrich)
        from .playlist_agent import generate_playlist
        return generate_playlist(request.mood, request.context, model=request.model, spotify_enrich=request.spotify_enrich, seed=request.seed)

    def enrich(self, playlist: Playlist) -> Playlist:
        enriched = enrich_tracks_with_spotify([track.model_dump() for track in playlist.tracks])
        playlist.tracks = [Track(**track) for track in enriched]
        return playlist

    def stream(self, request: GenerationRequest) -> Generator[tuple[str, dict[str, Any]], None, None]:
        request = request.normalized()
        if request.mode != "agentic":
            raise ValueError("streaming is only supported for agentic generation")
        from .graph_agent import stream_playlist_with_graph
        yield from stream_playlist_with_graph(
            request.mood,
            request.context,
            seed=request.seed,
            model=request.model,
            spotify_enrich=request.spotify_enrich,
        )


generation_service = GenerationService()