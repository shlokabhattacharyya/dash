### IMPORT LIBRARIES AND SETUP
import httpx
import time

_cache = {"data": None, "fetched_at": 0}
CACHE_TTL = 600 


### CONVERT WEATHER CODES TO DESCRIPTION
WMO_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "icy fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    80: "rain showers",
    81: "showers",
    82: "heavy showers",
    95: "thunderstorm",
    99: "thunderstorm",
}


### AUTO DETECT LAT/LON FROM IP ADDRESSS
def get_location():
    try:
        r = httpx.get("https://ipapi.co/json", timeout=5)
        d = r.json()
        return d["latitude"], d["longitude"], d["city"]
    except Exception:
        # fallback to new york
        return 40.71, -74.01, "new york"


### FETCH WEATHER
def fetch_weather():
    now = time.time()
    if _cache["data"] and (now - _cache["fetched_at"]) < CACHE_TTL:
        return _cache["data"]

    try:
        lat, lon, city = get_location()

        r = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": ["temperature_2m", "weathercode", "windspeed_10m", "relativehumidity_2m", "winddirection_10m"],
                "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_probability_max"],
                "temperature_unit": "fahrenheit",
                "windspeed_unit": "mph",
                "forecast_days": 1,
                "timezone": "auto",
            },
            timeout=5,
        )
        d = r.json()
        c = d["current"]
        day = d["daily"]

        desc = WMO_CODES.get(c["weathercode"], "unknown")

        # convert wind direction degrees to cardinal
        deg = c.get("winddirection_10m", 0)
        dirs = ["n","ne","e","se","s","sw","w","nw"]
        cardinal = dirs[round(deg / 45) % 8]

        data = {
            "temp": round(c["temperature_2m"]),
            "desc": desc,
            "hi": round(day["temperature_2m_max"][0]),
            "lo": round(day["temperature_2m_min"][0]),
            "wind": round(c["windspeed_10m"]),
            "wind_dir": cardinal.upper(),
            "humidity": round(c["relativehumidity_2m"]),
            "rain": day["precipitation_probability_max"][0],
            "city": city,
        }

        _cache["data"] = data
        _cache["fetched_at"] = now
        return data

    except Exception:
        return {
            "temp": "--", "desc": "unavailable", "hi": "--", "lo": "--",
            "wind": "--", "wind_dir": "--", "humidity": "--", "rain": "--",
            "city": "--",
        }


### FORMAT WEATHER (single line for dashboard)
def fmt_weather(w):
    return (
        f"{w['temp']}°f · {w['desc']} · "
        f"hi {w['hi']} lo {w['lo']} · "
        f"wind {w['wind']}mph {w['wind_dir']} · "
        f"rain {w['rain']}% · "
        f"humid {w['humidity']}%"
    )