"""
weather_gov_api.py
------------------
Fetch current weather, hourly forecast, 7-day forecast, active alerts,
and news headlines for a location using the free weather.gov REST API
+ OpenStreetMap Nominatim geocoding.
No API key required. No extra dependencies beyond stdlib.

Usage:
    python weather_gov_api.py "Cary, NC"
    python weather_gov_api.py "Cary, NC, USA"
    python weather_gov_api.py              # uses built-in default
"""

import json
import os
import re
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta


DEFAULT_LOCATION = "Cary, NC, USA"
_UA = "weather-gov-api-script/1.0 (educational use)"


def location_slug(location: str) -> str:
    return re.sub(r"[,\s]+", "_", location).strip("_")


def _get(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _UA, "Accept": "application/geo+json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def geocode(location: str) -> tuple[float, float]:
    """OSM Nominatim: location string → (lat, lon)."""
    params = urllib.parse.urlencode({"q": location, "format": "json", "limit": 1})
    req = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": _UA},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        results = json.loads(resp.read())
    if not results:
        raise ValueError(f"Could not geocode {location!r}")
    return float(results[0]["lat"]), float(results[0]["lon"])


def _parse_iso_duration_hours(duration: str) -> float:
    """Parse ISO 8601 durations like PT1H, P1DT6H into fractional hours."""
    m = re.match(r'P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$', duration)
    if not m:
        return 1.0
    d = int(m.group(1) or 0)
    h = int(m.group(2) or 0)
    mn = int(m.group(3) or 0)
    return d * 24 + h + mn / 60.0


def _grid_value_at(series: list, dt: datetime):
    """Return the gridpoint series value whose interval contains dt."""
    for entry in series:
        try:
            ts, dur = entry["validTime"].split("/")
            start = datetime.fromisoformat(ts)
            end = start + timedelta(hours=_parse_iso_duration_hours(dur))
            if start <= dt < end:
                return entry["value"]
        except Exception:
            continue
    return None


def _c_to_f(c):
    return round(c * 9 / 5 + 32, 1) if c is not None else None


def _fmt_time(iso: str) -> str:
    """Format ISO datetime like '2026-05-08T21:00:00-04:00' → '9 PM Thu'."""
    dt = datetime.fromisoformat(iso)
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{hour} {ampm} {dt.strftime('%a')}"


def fetch_weather(location: str = DEFAULT_LOCATION) -> dict:
    print(f"[1/8] Geocoding {location!r} ...")
    lat, lon = geocode(location)
    print(f"      lat={lat:.4f}, lon={lon:.4f}")

    print(f"[2/8] Fetching NWS grid point ...")
    point = _get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")
    props = point["properties"]
    forecast_url = props["forecast"]
    forecast_hourly_url = props["forecastHourly"]
    stations_url = props["observationStations"]
    office = props["cwa"]
    grid_x, grid_y = props["gridX"], props["gridY"]
    tz = props.get("timeZone", "UTC")
    rel = props.get("relativeLocation", {}).get("properties", {})
    resolved = f"{rel.get('city', '')}, {rel.get('state', '')}".strip(", ")

    print(f"[3/8] Fetching current conditions ...")
    stations = _get(stations_url)
    station_id = stations["features"][0]["properties"]["stationIdentifier"]
    obs = _get(f"https://api.weather.gov/stations/{station_id}/observations/latest")["properties"]

    def val(key):
        return (obs.get(key) or {}).get("value")

    temp_c = val("temperature")
    wind_ms = val("windSpeed")
    wind_gust_ms = val("windGust")
    dewpoint_c = val("dewpoint")
    humidity = val("relativeHumidity")
    visibility_m = val("visibility")
    pressure_pa = val("barometricPressure")

    current = {
        "station": station_id,
        "timestamp": obs.get("timestamp"),
        "description": obs.get("textDescription", ""),
        "temperature_f": _c_to_f(temp_c),
        "temperature_c": round(temp_c, 1) if temp_c is not None else None,
        "feels_like_f": None,
        "feels_like_c": None,
        "dewpoint_f": _c_to_f(dewpoint_c),
        "dewpoint_c": round(dewpoint_c, 1) if dewpoint_c is not None else None,
        "humidity_pct": round(humidity, 1) if humidity is not None else None,
        "wind_speed_mph": round(wind_ms * 2.237, 1) if wind_ms is not None else None,
        "wind_gust_mph": round(wind_gust_ms * 2.237, 1) if wind_gust_ms is not None else None,
        "wind_direction_deg": val("windDirection"),
        "visibility_miles": round(visibility_m / 1609.34, 1) if visibility_m is not None else None,
        "pressure_mb": round(pressure_pa / 100, 1) if pressure_pa is not None else None,
    }

    print(f"[4/8] Fetching 7-day forecast ...")
    forecast_periods = []
    for p in _get(forecast_url)["properties"]["periods"]:
        dp_c = (p.get("dewpoint") or {}).get("value")
        rh = (p.get("relativeHumidity") or {}).get("value")
        precip = (p.get("probabilityOfPrecipitation") or {}).get("value")
        forecast_periods.append({
            "name": p["name"],
            "is_daytime": p["isDaytime"],
            "temperature": f"{p['temperature']} °{p['temperatureUnit']}",
            "wind_speed": p.get("windSpeed", ""),
            "wind_direction": p.get("windDirection", ""),
            "short_forecast": p["shortForecast"],
            "detailed_forecast": p["detailedForecast"],
            "precip_pct": int(precip) if precip is not None else None,
            "dewpoint_f": _c_to_f(dp_c),
            "humidity_pct": round(rh, 1) if rh is not None else None,
        })

    print(f"[5/8] Fetching hourly forecast (24 hrs) ...")
    hourly_periods = []
    for p in _get(forecast_hourly_url)["properties"]["periods"][:24]:
        dp_c = (p.get("dewpoint") or {}).get("value")
        rh = (p.get("relativeHumidity") or {}).get("value")
        precip = (p.get("probabilityOfPrecipitation") or {}).get("value")
        hourly_periods.append({
            "time": p["startTime"],
            "temperature_f": p["temperature"],
            "feels_like_f": None,
            "dewpoint_f": _c_to_f(dp_c),
            "humidity_pct": round(rh, 1) if rh is not None else None,
            "wind_speed": p.get("windSpeed", ""),
            "wind_direction": p.get("windDirection", ""),
            "short_forecast": p["shortForecast"],
            "precip_pct": int(precip) if precip is not None else None,
        })

    print(f"[6/8] Fetching gridpoint data (feels like) ...")
    gprops = _get(f"https://api.weather.gov/gridpoints/{office}/{grid_x},{grid_y}")["properties"]
    apparent_series = gprops.get("apparentTemperature", {}).get("values", [])

    now = datetime.now(timezone.utc)
    app_c_now = _grid_value_at(apparent_series, now)
    current["feels_like_f"] = _c_to_f(app_c_now)
    current["feels_like_c"] = round(app_c_now, 1) if app_c_now is not None else None

    for p in hourly_periods:
        dt = datetime.fromisoformat(p["time"])
        app_c = _grid_value_at(apparent_series, dt)
        p["feels_like_f"] = _c_to_f(app_c)

    print(f"[7/8] Fetching active alerts ...")
    alerts = []
    for feature in _get(f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}").get("features", []):
        ap = feature["properties"]
        alerts.append({
            "event": ap.get("event", ""),
            "headline": ap.get("headline", ""),
            "severity": ap.get("severity", ""),
            "urgency": ap.get("urgency", ""),
            "effective": ap.get("effective", ""),
            "expires": ap.get("expires", ""),
            "description": ap.get("description", ""),
            "instruction": ap.get("instruction", ""),
        })

    print(f"[8/8] Fetching office news headlines ({office}) ...")
    headlines = []
    for item in _get(f"https://api.weather.gov/offices/{office}/headlines").get("@graph", []):
        headlines.append({
            "title": item.get("name", ""),
            "summary": item.get("title", ""),
            "url": item.get("@id", ""),
            "issued": item.get("issuanceTime", ""),
        })

    return {
        "location": location,
        "resolved_city": resolved,
        "coordinates": {"lat": lat, "lon": lon},
        "timezone": tz,
        "grid": {"office": office, "x": grid_x, "y": grid_y},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_conditions": current,
        "hourly_forecast": hourly_periods,
        "seven_day_forecast": forecast_periods,
        "active_alerts": alerts,
        "news_headlines": headlines,
    }


def fetch_current(location: str = DEFAULT_LOCATION) -> dict:
    """Lightweight fetch: current conditions only (4 API calls instead of 8)."""
    print(f"[1/4] Geocoding {location!r} ...")
    lat, lon = geocode(location)
    print(f"      lat={lat:.4f}, lon={lon:.4f}")

    print(f"[2/4] Fetching NWS grid point ...")
    point = _get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")
    props = point["properties"]
    stations_url = props["observationStations"]
    office = props["cwa"]
    grid_x, grid_y = props["gridX"], props["gridY"]
    tz = props.get("timeZone", "UTC")
    rel = props.get("relativeLocation", {}).get("properties", {})
    resolved = f"{rel.get('city', '')}, {rel.get('state', '')}".strip(", ")

    print(f"[3/4] Fetching current conditions ...")
    stations = _get(stations_url)
    station_id = stations["features"][0]["properties"]["stationIdentifier"]
    obs = _get(f"https://api.weather.gov/stations/{station_id}/observations/latest")["properties"]

    def val(key):
        return (obs.get(key) or {}).get("value")

    temp_c = val("temperature")
    wind_ms = val("windSpeed")
    wind_gust_ms = val("windGust")
    dewpoint_c = val("dewpoint")
    humidity = val("relativeHumidity")
    visibility_m = val("visibility")
    pressure_pa = val("barometricPressure")

    current = {
        "station": station_id,
        "timestamp": obs.get("timestamp"),
        "description": obs.get("textDescription", ""),
        "temperature_f": _c_to_f(temp_c),
        "temperature_c": round(temp_c, 1) if temp_c is not None else None,
        "feels_like_f": None,
        "feels_like_c": None,
        "dewpoint_f": _c_to_f(dewpoint_c),
        "dewpoint_c": round(dewpoint_c, 1) if dewpoint_c is not None else None,
        "humidity_pct": round(humidity, 1) if humidity is not None else None,
        "wind_speed_mph": round(wind_ms * 2.237, 1) if wind_ms is not None else None,
        "wind_gust_mph": round(wind_gust_ms * 2.237, 1) if wind_gust_ms is not None else None,
        "wind_direction_deg": val("windDirection"),
        "visibility_miles": round(visibility_m / 1609.34, 1) if visibility_m is not None else None,
        "pressure_mb": round(pressure_pa / 100, 1) if pressure_pa is not None else None,
    }

    print(f"[4/4] Fetching gridpoint data (feels like) ...")
    gprops = _get(f"https://api.weather.gov/gridpoints/{office}/{grid_x},{grid_y}")["properties"]
    apparent_series = gprops.get("apparentTemperature", {}).get("values", [])
    app_c_now = _grid_value_at(apparent_series, datetime.now(timezone.utc))
    current["feels_like_f"] = _c_to_f(app_c_now)
    current["feels_like_c"] = round(app_c_now, 1) if app_c_now is not None else None

    return {
        "location": location,
        "resolved_city": resolved,
        "coordinates": {"lat": lat, "lon": lon},
        "timezone": tz,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_conditions": current,
    }


def _opt(value, suffix="", default="N/A"):
    return f"{value}{suffix}" if value is not None else default


def to_markdown(data: dict) -> str:
    loc = data["location"]
    if data.get("resolved_city") and data["resolved_city"] != loc:
        loc += f" ({data['resolved_city']})"

    lines = [
        f"# Weather Report: {loc}",
        "",
        f"**Generated:** {data['generated_at']}  ",
        f"**Coordinates:** {data['coordinates']['lat']:.4f}, {data['coordinates']['lon']:.4f}  ",
        f"**Timezone:** {data['timezone']}",
        "",
    ]

    # Current conditions
    cur = data["current_conditions"]
    lines += [
        "## Current Conditions",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Station | {cur['station']} |",
        f"| As of | {cur['timestamp'] or 'N/A'} |",
        f"| Description | {cur['description'] or 'N/A'} |",
        f"| Temperature | {_opt(cur['temperature_f'], ' °F')} ({_opt(cur['temperature_c'], ' °C')}) |",
        f"| Feels Like | {_opt(cur['feels_like_f'], ' °F')} ({_opt(cur['feels_like_c'], ' °C')}) |",
        f"| Dew Point | {_opt(cur['dewpoint_f'], ' °F')} ({_opt(cur['dewpoint_c'], ' °C')}) |",
        f"| Humidity | {_opt(cur['humidity_pct'], '%')} |",
        f"| Wind Speed | {_opt(cur['wind_speed_mph'], ' mph')} |",
        f"| Wind Gusts | {_opt(cur['wind_gust_mph'], ' mph')} |",
        f"| Wind Direction | {_opt(cur['wind_direction_deg'], '°')} |",
        f"| Visibility | {_opt(cur['visibility_miles'], ' mi')} |",
        f"| Pressure | {_opt(cur['pressure_mb'], ' mb')} |",
        "",
    ]

    # Hourly forecast
    lines += ["## Hourly Forecast (Next 24 Hours)", ""]
    lines += ["| Time | Temp | Feels Like | Precip % | Humidity | Wind | Conditions |"]
    lines += ["|------|------|------------|----------|----------|------|------------|"]
    for p in data.get("hourly_forecast", []):
        time_str = _fmt_time(p["time"])
        temp = _opt(p["temperature_f"], " °F")
        feels = _opt(p["feels_like_f"], " °F")
        precip = _opt(p["precip_pct"], "%")
        humid = _opt(p["humidity_pct"], "%")
        wind = f"{p['wind_speed']} {p['wind_direction']}".strip()
        lines += [f"| {time_str} | {temp} | {feels} | {precip} | {humid} | {wind} | {p['short_forecast']} |"]
    lines += [""]

    # Active alerts
    lines += ["## Active Alerts", ""]
    if data["active_alerts"]:
        for alert in data["active_alerts"]:
            lines += [
                f"### {alert['event']}",
                "",
                f"**Severity:** {alert['severity']} | **Urgency:** {alert['urgency']}  ",
                f"**Headline:** {alert['headline']}  ",
                f"**Effective:** {alert['effective']}  ",
                f"**Expires:** {alert['expires']}",
                "",
                alert["description"],
                "",
            ]
            if alert.get("instruction"):
                lines += [f"**Instructions:** {alert['instruction']}", ""]
    else:
        lines += ["No active alerts.", ""]

    # News headlines
    lines += ["## News Headlines", ""]
    if data.get("news_headlines"):
        for h in data["news_headlines"]:
            title = h["title"] or h["summary"] or "Untitled"
            link = f"[{title}]({h['url']})" if h.get("url") else title
            issued = f"  \n  **Issued:** {h['issued']}" if h.get("issued") else ""
            summary = h["summary"] if h["summary"] and h["summary"] != h["title"] else ""
            lines += [f"- {link}{issued}"]
            if summary:
                lines += [f"  {summary}"]
        lines += [""]
    else:
        lines += ["No news headlines available.", ""]

    # 7-day forecast
    lines += ["## 7-Day Forecast", ""]
    for p in data["seven_day_forecast"]:
        precip = f" | Precip: {p['precip_pct']}%" if p.get("precip_pct") is not None else ""
        humid = f" | Humidity: {p['humidity_pct']}%" if p.get("humidity_pct") is not None else ""
        dp = f" | Dew Point: {p['dewpoint_f']} °F" if p.get("dewpoint_f") is not None else ""
        lines += [
            f"### {p['name']}",
            "",
            f"**{p['temperature']}** — {p['short_forecast']}{precip}{humid}{dp}  ",
            f"Wind: {p['wind_speed']} {p['wind_direction']}",
            "",
            p["detailed_forecast"],
            "",
        ]

    return "\n".join(lines)


def to_markdown_now(data: dict) -> str:
    loc = data["location"]
    if data.get("resolved_city") and data["resolved_city"] != loc:
        loc += f" ({data['resolved_city']})"

    cur = data["current_conditions"]
    lines = [
        f"# Current Conditions: {loc}",
        "",
        f"**Generated:** {data['generated_at']}  ",
        f"**Coordinates:** {data['coordinates']['lat']:.4f}, {data['coordinates']['lon']:.4f}  ",
        f"**Timezone:** {data['timezone']}",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Station | {cur['station']} |",
        f"| As of | {cur['timestamp'] or 'N/A'} |",
        f"| Description | {cur['description'] or 'N/A'} |",
        f"| Temperature | {_opt(cur['temperature_f'], ' °F')} ({_opt(cur['temperature_c'], ' °C')}) |",
        f"| Feels Like | {_opt(cur['feels_like_f'], ' °F')} ({_opt(cur['feels_like_c'], ' °C')}) |",
        f"| Dew Point | {_opt(cur['dewpoint_f'], ' °F')} ({_opt(cur['dewpoint_c'], ' °C')}) |",
        f"| Humidity | {_opt(cur['humidity_pct'], '%')} |",
        f"| Wind Speed | {_opt(cur['wind_speed_mph'], ' mph')} |",
        f"| Wind Gusts | {_opt(cur['wind_gust_mph'], ' mph')} |",
        f"| Wind Direction | {_opt(cur['wind_direction_deg'], '°')} |",
        f"| Visibility | {_opt(cur['visibility_miles'], ' mi')} |",
        f"| Pressure | {_opt(cur['pressure_mb'], ' mb')} |",
    ]
    return "\n".join(lines)


def main(location: str = DEFAULT_LOCATION, now: bool = False, output_dir: str = "output"):
    slug = location_slug(location)
    os.makedirs(output_dir, exist_ok=True)

    if now:
        data = fetch_current(location)
        json_file = os.path.join(output_dir, f"{slug}_NOW.json")
        md_file = os.path.join(output_dir, f"{slug}_NOW.md")
        md_content = to_markdown_now(data)
    else:
        data = fetch_weather(location)
        json_file = os.path.join(output_dir, f"{slug}_API.json")
        md_file = os.path.join(output_dir, f"{slug}_API.md")
        md_content = to_markdown(data)

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nSaved JSON     -> {json_file}")

    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Saved Markdown -> {md_file}")


if __name__ == "__main__":
    args = sys.argv[1:]
    now_flag = "--now" in args
    args = [a for a in args if a != "--now"]

    output_dir = "output"
    if "--output" in args:
        idx = args.index("--output")
        output_dir = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    loc = " ".join(args) if args else DEFAULT_LOCATION
    main(loc, now=now_flag, output_dir=output_dir)
