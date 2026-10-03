"""FastAPI backend — exposes VibeForge pipeline over HTTP/SSE."""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated, Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

load_dotenv()

from vibeforge.application import GenerationRequest, generation_service
from vibeforge.models import Playlist
from vibeforge.utils import DEFAULT_MODEL, AVAILABLE_MODELS

logger = logging.getLogger(__name__)

app = FastAPI(title="VibeForge API", version="1.0.0")

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "VIBEFORGE_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://192.168.2.142:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response schemas ────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    mood: str = Field(min_length=1, max_length=500)
    context: str = Field(default="", max_length=500)
    seed: str = Field(default="", max_length=200)
    model: str = DEFAULT_MODEL
    mode: Literal["fast", "deep", "agentic"] = "fast"
    spotify_enrich: bool = True

    def to_application_request(self) -> GenerationRequest:
        return GenerationRequest(**self.model_dump())


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/models")
def list_models() -> list[str]:
    return AVAILABLE_MODELS


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate")
def generate(req: GenerateRequest) -> dict[str, Any]:
    """Return a playlist immediately; Spotify enrichment is handled separately."""
    try:
        return generation_service.generate(req.to_application_request(), defer_enrichment=True).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("Playlist generation failed")
        raise HTTPException(status_code=503, detail="Playlist generation is temporarily unavailable") from None


@app.post("/enrich")
def enrich(req: Playlist) -> dict[str, Any]:
    """Best-effort Spotify enrichment after the playlist has reached the client."""
    try:
        return generation_service.enrich(req).model_dump()
    except Exception:
        logger.exception("Playlist enrichment failed")
        return req.model_dump()


class FeedbackTrack(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    artist: str = Field(min_length=1, max_length=200)


class FeedbackRequest(BaseModel):
    loved: list[FeedbackTrack] = Field(default_factory=list[FeedbackTrack], max_length=200)
    disliked: list[FeedbackTrack] = Field(default_factory=list[FeedbackTrack], max_length=200)


@app.post("/feedback")
def feedback(req: FeedbackRequest) -> dict[str, bool]:
    from vibeforge.memory import save_feedback
    save_feedback(
        [track.model_dump() for track in req.loved],
        [track.model_dump() for track in req.disliked],
    )
    generation_service.invalidate_cache()
    return {"saved": True}


@app.get("/stream")
def stream(
    mood: Annotated[str, Query()],
    context: Annotated[str, Query()] = "",
    seed: Annotated[str, Query()] = "",
    model: Annotated[str, Query()] = DEFAULT_MODEL,
    spotify_enrich: Annotated[bool, Query()] = True,
) -> StreamingResponse:
    """Agentic mode — streams SSE events, one per graph node."""
    request = GenerationRequest(
        mood=mood,
        context=context,
        seed=seed,
        model=model,
        mode="agentic",
        spotify_enrich=spotify_enrich,
    )

    def event_generator():
        try:
            for node_name, state in generation_service.stream(request):
                payload: dict[str, Any] = {"node": node_name}

                if node_name == "analyse_mood" and state.get("mood_analysis"):
                    ma = state["mood_analysis"]
                    payload["data"] = {
                        "emotion": ma.primary_emotion,
                        "energy": ma.energy_level,
                        "bpm_range": ma.bpm_range,
                        "occasion": ma.occasion,
                    }
                elif node_name == "critique_playlist" and state.get("critique"):
                    c = state["critique"]
                    payload["data"] = {"score": c.score, "feedback": c.feedback}
                elif node_name == "curate_playlist":
                    payload["data"] = {"attempt": state.get("refinement_attempts", 0)}
                elif node_name == "finalise" and state.get("playlist"):
                    payload["data"] = state["playlist"].model_dump()

                yield f"data: {json.dumps(payload)}\n\n"

            yield "data: {\"node\": \"done\"}\n\n"
        except ValueError as exc:
            yield f"data: {json.dumps({'node': 'error', 'message': str(exc)})}\n\n"
        except Exception:
            logger.exception("Playlist stream failed")
            yield 'data: {"node": "error", "message": "Playlist generation is temporarily unavailable"}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
