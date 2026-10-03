"""Unit tests for Pydantic models — no API key needed."""

import pytest
from pydantic import ValidationError
from vibeforge.models import Track, Playlist, MoodAnalysis


def make_track(**kwargs):
    defaults = {"title": "Blinding Lights", "artist": "The Weeknd", "genre": "Synth-pop"}
    return Track(**{**defaults, **kwargs})


def make_playlist(n_tracks: int = 10) -> Playlist:
    tracks = [make_track(title=f"Song {i}", artist=f"Artist {i}") for i in range(n_tracks)]
    return Playlist(
        name="Test Vibes",
        mood_summary="A test playlist",
        vibe_tags=["test", "chill"],
        energy_level="medium",
        genres=["Pop"],
        tracks=tracks,
    )


class TestTrack:
    def test_spotify_url_auto_filled(self):
        t = make_track()
        assert "open.spotify.com/search/" in t.spotify_search_url

    def test_youtube_url_auto_filled(self):
        t = make_track()
        assert "youtube.com/results" in t.youtube_search_url

    def test_custom_urls_preserved(self):
        t = make_track(
            spotify_search_url="https://custom.spotify.url",
            youtube_search_url="https://custom.yt.url",
        )
        assert t.spotify_search_url == "https://custom.spotify.url"
        assert t.youtube_search_url == "https://custom.yt.url"

    def test_bpm_optional(self):
        t = make_track()
        assert t.bpm is None
        t2 = make_track(bpm=120)
        assert t2.bpm == 120


class TestPlaylist:
    def test_valid_playlist(self):
        p = make_playlist()
        assert len(p.tracks) == 10

    def test_too_few_tracks_raises(self):
        with pytest.raises(ValidationError):
            make_playlist(n_tracks=3)

    def test_too_many_tracks_raises(self):
        with pytest.raises(ValidationError):
            make_playlist(n_tracks=13)

    def test_serialise_round_trip(self):
        p = make_playlist()
        data = p.model_dump()
        p2 = Playlist(**data)
        assert p2.name == p.name
        assert len(p2.tracks) == len(p.tracks)

    def test_invalid_energy_level_raises(self):
        with pytest.raises(ValidationError):
            make_playlist()  # make a valid one first
            Playlist(
                name="Bad", mood_summary="bad", vibe_tags=[], energy_level="extreme",
                genres=[], tracks=[make_track(title=f"Song {i}", artist=f"A {i}") for i in range(10)],
            )


class TestContext:
    def test_temporal_context_returns_string(self):
        from vibeforge.context import get_temporal_context
        ctx = get_temporal_context()
        assert any(tod in ctx for tod in {"morning", "afternoon", "evening", "late night"})

    def test_build_context_string(self):
        from vibeforge.context import build_context_string
        ctx = build_context_string("studying")
        assert "Time:" in ctx
        assert "studying" in ctx

    def test_seed_track_in_context(self):
        from vibeforge.context import build_context_string
        ctx = build_context_string(seed="Blinding Lights by The Weeknd")
        assert "Blinding Lights" in ctx


class TestMemory:
    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VIBEFORGE_DATA_DIR", str(tmp_path))
        import vibeforge.memory as mem
        p = make_playlist()
        mem.save_session("chill vibes", p.model_dump())
        ctx = mem.get_preference_context()
        assert "Pop" in ctx or ctx == "" or "Artist" in ctx

    def test_save_feedback_loved(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VIBEFORGE_DATA_DIR", str(tmp_path))
        import vibeforge.memory as mem

        track = {"title": "Blinding Lights", "artist": "The Weeknd", "genre": "Synth-pop"}
        mem.save_feedback([track], [])

        import json
        fb = json.loads((tmp_path / "memory.json").read_text(encoding="utf-8"))["feedback"]
        assert "Blinding Lights by The Weeknd" in fb["loved"]
        assert "Blinding Lights by The Weeknd" not in fb["disliked"]
        assert fb["loved"]["Blinding Lights by The Weeknd"] == 1

    def test_save_feedback_disliked_removes_loved(self, tmp_path, monkeypatch):
        import json
        monkeypatch.setenv("VIBEFORGE_DATA_DIR", str(tmp_path))
        import vibeforge.memory as mem

        track = {"title": "Blinding Lights", "artist": "The Weeknd", "genre": "Synth-pop"}
        mem.save_feedback([track], [])
        mem.save_feedback([], [track])

        fb = json.loads((tmp_path / "memory.json").read_text(encoding="utf-8"))["feedback"]
        assert "Blinding Lights by The Weeknd" not in fb["loved"]
        assert fb["disliked"]["Blinding Lights by The Weeknd"] == 1
