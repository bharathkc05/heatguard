from datetime import datetime
import os

import httpx
import numpy as np

OWM_API_KEY = os.getenv("OWM_API_KEY", "your_key_here")
OWM_URL = "https://api.openweathermap.org/data/2.5/weather"

# Climate zone detection from GPS coordinates
ZONE_BOXES = {
    "Hot_Dry": {"lat": (20.0, 30.0), "lon": (68.0, 78.0)},
    "Hot_Humid": {"lat": (8.0, 20.0), "lon": (74.0, 88.0)},
    "Semi_Arid": {"lat": (13.0, 21.0), "lon": (74.0, 82.0)},
    "Composite": {"lat": (24.0, 32.0), "lon": (74.0, 88.0)},
    "Highland": {"lat": (25.0, 35.0), "lon": (76.0, 97.0)},
}

ZONE_ENC = {
    "Highland": 0,
    "Hot_Humid": 1,
    "Semi_Arid": 2,
    "Composite": 3,
    "Hot_Dry": 4,
}


def detect_climate_zone(lat: float, lon: float) -> str:
    for zone, box in ZONE_BOXES.items():
        if box["lat"][0] <= lat <= box["lat"][1] and box["lon"][0] <= lon <= box["lon"][1]:
            return zone
    return "Semi_Arid"  # default fallback


async def fetch_weather(lat: float, lon: float) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                OWM_URL,
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": OWM_API_KEY,
                    "units": "metric",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        tdb = data["main"]["temp"]
        rh = data["main"]["humidity"]
        wind_speed = data["wind"].get("speed", 2.0)
    except Exception:
        # Fallback keeps API responsive in local/offline/invalid-key setups.
        zone = detect_climate_zone(lat, lon)
        fallback = {
            "Hot_Dry": {"tdb": 38.0, "rh": 28.0, "v": 2.2},
            "Hot_Humid": {"tdb": 34.0, "rh": 78.0, "v": 2.0},
            "Semi_Arid": {"tdb": 36.0, "rh": 45.0, "v": 2.3},
            "Composite": {"tdb": 35.0, "rh": 58.0, "v": 2.1},
            "Highland": {"tdb": 26.0, "rh": 60.0, "v": 1.8},
        }[zone]
        tdb = fallback["tdb"]
        rh = fallback["rh"]
        wind_speed = fallback["v"]

    # Mean radiant temperature approximation from tdb + solar load
    hour = datetime.utcnow().hour
    solar_factor = max(0.0, np.sin(np.pi * (hour - 6) / 12)) if 6 <= hour <= 18 else 0.0
    tr = tdb + solar_factor * 12.0

    return {
        "tdb": tdb,
        "rh": rh,
        "v": wind_speed,
        "tr": tr,
    }


def compute_wbgt(tdb: float, rh: float, tr: float, v: float) -> float:
    rh_c = max(rh, 5.0)
    twb = (
        tdb * np.arctan(0.151977 * (rh_c + 8.313659) ** 0.5)
        + np.arctan(tdb + rh_c)
        - np.arctan(rh_c - 1.676331)
        + 0.00391838 * rh_c ** 1.5 * np.arctan(0.023101 * rh_c)
        - 4.686035
    )
    tg = max(tr - (1.5 * v), tdb - 2.0)
    wbgt = 0.7 * twb + 0.2 * tg + 0.1 * tdb
    return max(wbgt, 10.0)


def compute_heat_index(tdb: float, rh: float) -> float:
    if tdb <= 27.0 or rh <= 40.0:
        return tdb
    return (
        -8.78469475556
        + 1.61139411 * tdb
        + 2.33854883889 * rh
        - 0.14611605 * tdb * rh
        - 0.012308094 * tdb**2
        - 0.0164248277778 * rh**2
        + 0.002211732 * tdb**2 * rh
        + 0.00072546 * tdb * rh**2
        - 0.000003582 * tdb**2 * rh**2
    )
