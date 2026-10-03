from vibeforge.graph_agent import _finalise
from vibeforge.models import MoodAnalysis
from tests.test_models import make_playlist, make_track


def _state(playlist, mood_analysis=None, spotify_enrich=False):
    return {
        "mood_input": "focus",
        "playlist": playlist,
        "mood_analysis": mood_analysis,
        "critique": None,
        "spotify_enrich": spotify_enrich,
    }


def test_finalise_repairs_duplicate_and_keeps_playlist(monkeypatch):
    monkeypatch.setattr("vibeforge.graph_agent.save_session", lambda *a, **k: None)
    playlist = make_playlist()
    for i, t in enumerate(playlist.tracks):
        t.genre = f"Genre {i}"
    playlist.tracks[-1] = make_track(title="Song 0", artist="Artist 0", genre="Genre 9")

    result = _finalise(_state(playlist))

    assert len(result["playlist"].tracks) == 9


def test_finalise_raises_on_unrepairable_bpm_violation(monkeypatch):
    monkeypatch.setattr("vibeforge.graph_agent.save_session", lambda *a, **k: None)
    playlist = make_playlist()
    playlist.tracks[0].bpm = 500
    mood_analysis = MoodAnalysis(
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

    try:
        _finalise(_state(playlist, mood_analysis=mood_analysis))
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "hard rules" in str(e)
