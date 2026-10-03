from vibeforge.quality import repair_playlist, validate_playlist
from tests.test_models import make_playlist, make_track


def _distinct_genres(playlist):
    for i, t in enumerate(playlist.tracks):
        t.genre = f"Genre {i}"


def test_repair_playlist_drops_duplicate_track():
    playlist = make_playlist()
    _distinct_genres(playlist)
    playlist.tracks[-1] = make_track(title="Song 0", artist="Artist 0", genre="Genre 9")  # duplicate of track 0

    repair_playlist(playlist)

    keys = [f"{t.title.lower()} by {t.artist.lower()}" for t in playlist.tracks]
    assert len(keys) == len(set(keys))
    assert len(playlist.tracks) == 9


def test_repair_playlist_caps_artist_at_two():
    playlist = make_playlist()
    _distinct_genres(playlist)
    playlist.tracks[-3:] = [make_track(title=f"Extra {i}", artist="Artist 0", genre=f"Genre {7 + i}") for i in range(3)]

    repair_playlist(playlist)

    artist_counts = {}
    for t in playlist.tracks:
        artist_counts[t.artist.lower()] = artist_counts.get(t.artist.lower(), 0) + 1
    assert all(count <= 2 for count in artist_counts.values())
    assert not any("Artist diversity" in i for i in validate_playlist(playlist))


def test_repair_playlist_prefers_loved_track_when_trimming_artist_overflow():
    playlist = make_playlist()
    _distinct_genres(playlist)
    # track[0] is "Song 0 by Artist 0"; add two more Artist 0 tracks -> 3 total, cap is 2.
    playlist.tracks[-2:] = [
        make_track(title="Extra 0", artist="Artist 0", genre="Genre 8"),
        make_track(title="Extra 1", artist="Artist 0", genre="Genre 9"),
    ]

    repair_playlist(playlist, loved_keys=frozenset({"extra 1 by artist 0"}))

    titles = {t.title for t in playlist.tracks}
    assert "Extra 1" in titles  # loved track survives the artist cap
    assert "Extra 0" not in titles  # unrated track is the one dropped instead
