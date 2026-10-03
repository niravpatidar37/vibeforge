"""Optional Spotify API integration for real track links."""

import os
import base64
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


_token_cache: dict[str, Any] = {}


def _get_token() -> Optional[str]:
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        _token_cache.clear()
        return None

    # Reuse cached token if still valid
    access_token = _token_cache.get("access_token")
    expires_at = _token_cache.get("expires_at")
    if access_token and isinstance(expires_at, (int, float)) and time.time() < expires_at:
        return access_token

    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    try:
        resp = requests.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {creds}"},
            data={"grant_type": "client_credentials"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        access_token = data.get("access_token")
        if not access_token:
            return None
        expires_in = int(data.get("expires_in", 3600))
        _token_cache["access_token"] = access_token
        _token_cache["expires_at"] = time.time() + max(expires_in - 60, 0)
        return access_token
    except requests.RequestException as exc:
        logger.warning("Spotify token request failed: %s", exc)
        return None


def _enrich_one(track: dict[str, Any], token: str) -> dict[str, Any]:
    """Fetch a real Spotify URL for a single track; returns the track unchanged on failure."""
    query = f"track:{track.get('title', '')} artist:{track.get('artist', '')}"
    try:
        resp = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query, "type": "track", "limit": 1},
            timeout=8,
        )
        resp.raise_for_status()
        items = resp.json().get("tracks", {}).get("items", [])
        if items:
            track["spotify_search_url"] = items[0]["external_urls"]["spotify"]
    except requests.RequestException as exc:
        logger.warning("Spotify enrichment failed for '%s': %s", track.get("title"), exc)
    return track


def enrich_tracks_with_spotify(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Try to add real Spotify track URLs. Falls back to search URLs if API unavailable."""
    token = _get_token()
    if not token:
        return tracks  # search URLs already set in Track.model_post_init

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_enrich_one, track, token): i for i, track in enumerate(tracks)}
        result: list[dict[str, Any]] = [{} for _ in tracks]
        for future in as_completed(futures):
            result[futures[future]] = future.result()
    return result
