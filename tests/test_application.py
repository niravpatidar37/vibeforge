"""Application service contract tests that do not call external providers."""

import pytest
from pydantic import ValidationError

from vibeforge.application import GenerationRequest
from vibeforge.memory import _compact_sections
from vibeforge.utils import count_tokens, ensure_context_budget


def test_generation_request_normalizes_user_input():
    request = GenerationRequest(
        mood="  late night drive  ",
        context=" rainy city ",
        seed="  Blinding Lights  ",
    ).normalized()

    assert request.mood == "late night drive"
    assert request.context == "rainy city"
    assert request.seed == "Blinding Lights"


def test_generation_request_rejects_blank_mood():
    with pytest.raises(ValueError, match="non-whitespace"):
        GenerationRequest(mood="   ").normalized()


def test_generation_request_rejects_unknown_model():
    with pytest.raises(ValueError, match="model must be one of"):
        GenerationRequest(mood="focus", model="unknown-model").normalized()


def test_generation_request_rejects_unknown_mode():
    with pytest.raises(ValidationError):
        GenerationRequest(mood="focus", mode="experimental")


def test_count_tokens_uses_model_tokenizer_when_available():
    class Tokenizer:
        def encode(self, text, add_special_tokens=False):
            return text.split()

    assert count_tokens(Tokenizer(), "one two three") == 3


def test_context_budget_reserves_output_tokens():
    with pytest.raises(ValueError, match="Prompt is too large"):
        ensure_context_budget([type("Message", (), {"content": "x" * 400})()], context_limit=100, requested_output=20)


def test_preference_sections_are_compacted():
    result = _compact_sections(["loved tracks", "recent history", "disliked tracks"], max_chars=20)
    assert len(result) <= 20
    assert result.startswith("loved tracks")


def test_agentic_pipeline_allows_two_refinements():
    from vibeforge.graph_agent import PlaylistCritique, _route_after_critique

    critique = PlaylistCritique(score=5, issues=["needs work"], feedback="Improve it")
    base = {"critique": critique, "refinement_attempts": 0}

    assert _route_after_critique(base) == "refine"
    assert _route_after_critique({**base, "refinement_attempts": 1}) == "refine"
    assert _route_after_critique({**base, "refinement_attempts": 2}) == "finalise"


def test_generation_service_caches_base_playlist(monkeypatch):
    from vibeforge.application import GenerationService
    from tests.test_models import make_playlist

    service = GenerationService()
    playlist = make_playlist()
    for index, track in enumerate(playlist.tracks):
        track.genre = f"Genre {index}"
    calls = 0

    def generate(_request):
        nonlocal calls
        calls += 1
        return playlist

    monkeypatch.setattr(service, "_generate_uncached", generate)
    request = GenerationRequest(mood="focus", spotify_enrich=False)

    first = service.generate(request)
    second = service.generate(request)

    assert calls == 1
    assert first is not second
    assert first.name == second.name


def test_generation_service_rejects_invalid_generated_playlist(monkeypatch):
    from vibeforge.application import GenerationService
    from tests.test_models import make_playlist

    service = GenerationService()
    playlist = make_playlist()
    monkeypatch.setattr(service, "_generate_uncached", lambda _request: playlist)

    with pytest.raises(RuntimeError, match="hard validation"):
        service.generate(GenerationRequest(mood="focus", spotify_enrich=False))


def test_generation_service_accepts_repaired_agentic_playlist_under_ten_tracks(monkeypatch):
    from vibeforge.application import GenerationService
    from vibeforge.quality import repair_playlist
    from tests.test_models import make_playlist, make_track

    playlist = make_playlist()
    for i, t in enumerate(playlist.tracks):
        t.genre = f"Genre {i}"
    playlist.tracks[-1] = make_track(title="Song 0", artist="Artist 0", genre="Genre 9")  # duplicate
    repair_playlist(playlist)
    assert len(playlist.tracks) == 9  # repair already dropped the duplicate before this point

    service = GenerationService()
    monkeypatch.setattr(service, "_generate_uncached", lambda _request: playlist)

    result = service.generate(GenerationRequest(mood="focus", mode="agentic", spotify_enrich=False))

    assert len(result.tracks) == 9


def test_generation_service_falls_back_to_in_process_cache_when_redis_unreachable(monkeypatch):
    from vibeforge.application import GenerationService

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1")  # nothing listens here
    service = GenerationService()

    assert service._redis is None  # connection failed, fell back cleanly


def test_generation_service_invalidate_cache_forgets_cached_playlist(monkeypatch):
    from vibeforge.application import GenerationService
    from tests.test_models import make_playlist

    service = GenerationService()
    playlist = make_playlist()
    for index, track in enumerate(playlist.tracks):
        track.genre = f"Genre {index}"
    calls = 0

    def generate(_request):
        nonlocal calls
        calls += 1
        return playlist

    monkeypatch.setattr(service, "_generate_uncached", generate)
    request = GenerationRequest(mood="focus", spotify_enrich=False)

    service.generate(request)
    service.invalidate_cache()
    service.generate(request)

    assert calls == 2


def test_generation_service_stream_passes_enrichment_setting(monkeypatch):
    import vibeforge.graph_agent as graph_agent
    from vibeforge.application import GenerationService

    observed: dict[str, bool] = {}

    def stream(_mood, _context, *, seed, model, spotify_enrich):
        observed["spotify_enrich"] = spotify_enrich
        yield "finalise", {"playlist": None}

    monkeypatch.setattr(graph_agent, "stream_playlist_with_graph", stream)
    request = GenerationRequest(mood="focus", mode="agentic", spotify_enrich=True)
    list(GenerationService().stream(request))

    assert observed["spotify_enrich"] is True


def test_deterministic_playlist_issues_skip_critic_model():
    from vibeforge.graph_agent import _critique_playlist
    from tests.test_models import make_playlist
    from vibeforge.models import MoodAnalysis

    playlist = make_playlist()
    for track in playlist.tracks[1:]:
        track.artist = playlist.tracks[0].artist
    analysis = MoodAnalysis(
        primary_emotion="focused",
        secondary_emotions=[],
        energy_level="low",
        bpm_range="60-80",
        recommended_genres=["ambient"],
        avoid_genres=[],
        time_of_day_context="evening",
        activity_context="reading",
        musical_key_feel="minor",
    )

    result = _critique_playlist({"playlist": playlist, "mood_input": "reading", "mood_analysis": analysis})

    assert result["critique"].score == 5
    assert "Artist diversity" in result["critique"].issues[0]


def test_playlist_rule_evaluator_returns_langsmith_score():
    from vibeforge.quality import playlist_rule_evaluator
    from tests.test_models import make_playlist

    playlist = make_playlist()
    for index, track in enumerate(playlist.tracks):
        track.genre = f"Genre {index}"
    result = playlist_rule_evaluator({}, {"playlist": playlist})

    assert result["key"] == "playlist_rules"
    assert result["score"] == 1.0