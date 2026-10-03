"""Gathers runtime context: time of day, season, weather."""

import logging
import os
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


def get_temporal_context() -> str:
    now = datetime.now()
    hour = now.hour
    day_name = now.strftime("%A")

    month = now.month
    if month in (12, 1, 2):
        season = "winter"
    elif month in (3, 4, 5):
        season = "spring"
    elif month in (6, 7, 8):
        season = "summer"
    else:
        season = "autumn"

    is_weekend = now.weekday() >= 5
    day_type = "weekend" if is_weekend else "weekday"

    if 5 <= hour < 12:
        tod = "morning"
    elif 12 <= hour < 17:
        tod = "afternoon"
    elif 17 <= hour < 21:
        tod = "evening"
    else:
        tod = "late night"

    return f"{day_name} {tod} ({day_type}, {season})"


def get_weather(city: str | None = None) -> str:
    """Return a short weather description, or empty string on failure."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    city = city or os.getenv("OPENWEATHER_CITY", "")
    if not api_key or not city:
        return ""
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        resp = requests.get(url, params={"q": city, "appid": api_key, "units": "metric"}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        weather_list = data.get("weather", [])
        main = data.get("main", {})
        desc = weather_list[0].get("description") if weather_list else None
        temp = main.get("temp")
        if desc is None or temp is None:
            logger.warning("Unexpected weather response shape for '%s'", city)
            return ""
        return f"{desc}, {temp:.0f}°C in {city}"
    except requests.RequestException as exc:
        logger.warning("Weather fetch failed for '%s': %s", city, exc)
        return ""


def build_context_string(extra: str = "", seed: str = "") -> str:
    parts = [f"Time: {get_temporal_context()}"]
    weather = get_weather()
    if weather:
        parts.append(f"Weather: {weather}")
    if extra:
        parts.append(f"Additional context: {extra}")
    if seed:
        parts.append(f"Seed track (use as vibe anchor — match this song's energy, era, and feel): {seed}")
    return "\n".join(parts)
