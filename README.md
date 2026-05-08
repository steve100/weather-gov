# weather-gov

Fetch current weather, hourly forecast, 7-day forecast, active alerts, and news
headlines for any US location using the free [weather.gov REST API](https://www.weather.gov/documentation/services-web-api).
No API key required.

Two scripts are provided:

| Script | Approach | Extra deps |
|--------|----------|------------|
| `weather_gov_api.py` | Calls the NWS REST API directly | none (stdlib only) |
| `weather_gov_playwrite.py` | Drives a real browser via Playwright | `playwright`, `html2text` |

---

## Requirements

**API script** — Python 3.12+, no extra packages.

**Playwright script** — install dependencies once.

### Install uv

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Create the virtual environment and install packages

```bash
uv init
uv venv
uv add playwright html2text
uv run playwright install chromium
```

### Activate the environment (optional — makes `python` and `playwright` available directly)

```bash
# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### pip alternative

```bash
pip install playwright html2text
playwright install chromium
```

---

## Usage

### `weather_gov_api.py`

```bash
# Full report — current conditions, hourly (24 hr), 7-day forecast, alerts, headlines
python weather_gov_api.py "Cary, NC, USA"
python weather_gov_api.py "Raleigh, NC"
python weather_gov_api.py                        # defaults to Cary, NC, USA

# Current conditions only (faster — 4 API calls instead of 8)
python weather_gov_api.py "Cary, NC" --now

# Write output to a custom directory (default: output/)
python weather_gov_api.py "Cary, NC" --output reports
python weather_gov_api.py "Cary, NC" --now --output /tmp/wx
```

**Output files**

| Mode | Files |
|------|-------|
| Full | `output/{Location}_API.json`, `output/{Location}_API.md` |
| `--now` | `output/{Location}_NOW.json`, `output/{Location}_NOW.md` |

---

### `weather_gov_playwrite.py`

Navigates to weather.gov in a Chromium browser, searches for the location, and
scrapes the forecast page.

```bash
# Full report — saves HTML, Markdown, JSON, and a full-page screenshot
python weather_gov_playwrite.py "Cary, NC, USA"
python weather_gov_playwrite.py "Raleigh, NC"
python weather_gov_playwrite.py                  # defaults to Cary, NC, USA

# Current conditions only — saves JSON and screenshot
python weather_gov_playwrite.py "Cary, NC" --now

# Write output to a custom directory (default: output/)
python weather_gov_playwrite.py "Cary, NC" --output reports
python weather_gov_playwrite.py "Cary, NC" --now --output /tmp/wx
```

**Output files**

| Mode | Files |
|------|-------|
| Full | `output/{Location}_playwrite.html`, `.md`, `.json`, `.png` |
| `--now` | `output/{Location}_NOW_playwrite.json`, `.png` |

---

## Output data

### JSON structure — full report (`_API.json`)

```
location               string
resolved_city          string
coordinates            { lat, lon }
timezone               string
grid                   { office, x, y }
generated_at           ISO 8601 timestamp
current_conditions     { station, timestamp, description, temperature_f/c,
                         feels_like_f/c, dewpoint_f/c, humidity_pct,
                         wind_speed_mph, wind_gust_mph, wind_direction_deg,
                         visibility_miles, pressure_mb }
hourly_forecast        [ 24 periods: time, temperature_f, feels_like_f,
                         dewpoint_f, humidity_pct, wind_speed, wind_direction,
                         short_forecast, precip_pct ]
seven_day_forecast     [ periods: name, temperature, wind_speed, wind_direction,
                         short_forecast, detailed_forecast, precip_pct,
                         dewpoint_f, humidity_pct ]
active_alerts          [ event, headline, severity, urgency, effective,
                         expires, description, instruction ]
news_headlines         [ title, summary, url, issued ]
```

### JSON structure — now report (`_NOW.json`)

```
location, resolved_city, coordinates, timezone, generated_at,
current_conditions     (same fields as above)
```

Example output files for Cary, NC are in the [`output/`](output/) folder.

---

## Tests

Tests are in the `tests/` directory and use Python's built-in `unittest` framework.

### Install pytest

```bash
uv add --dev pytest

# pip alternative
pip install pytest
```

### Run tests
```bash
# Windows Batch files - easily converted to BASH
run-tests.bat -  Discovers tests and writes  output to standard out
run-tests-junit.bat - Discovers tests and writes output ot output/junit.xml

```bash
# Simple run
python -m unittest discover tests

# Verbose output
python -m pytest tests -v

# With JUnit XML report (for CI or reporting tools)
python -m pytest tests --junitxml=junit.xml
```

### Auto-generate JUnit XML on every run

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "--junitxml=junit.xml"
```

Then `python -m pytest tests` always produces `junit.xml`.

### Test coverage

**`tests/test_weather_gov_api.py`** — unit tests for internal functions and renderers

| Class | What it covers |
|-------|---------------|
| `TestLocationSlug` | Slug generation from various location strings |
| `TestCToF` | Celsius → Fahrenheit conversion, `None` handling, rounding |
| `TestFmtTime` | AM/PM formatting, midnight and noon edge cases |
| `TestParseIsoDurationHours` | ISO 8601 durations: hours, days, minutes, invalid input |
| `TestGridValueAt` | Time-series lookup: exact match, within interval, before series, empty |
| `TestOpt` | Formatting helper: value, `None`, zero, custom default |
| `TestToMarkdownNow` | `--now` markdown output contains correct sections and values |
| `TestToMarkdown` | Full report markdown: all sections, precip%, alerts, headlines |
| `TestFetchCurrent` | Mocked API calls: correct keys, temperature conversion, bad location |

**`tests/test_cli.py`** — command-line interface tests using "Cary, NC, USA"

| Class | What it covers |
|-------|---------------|
| `TestCliArgParsing` | `--now` before/after location, `--output`, combined flags, no args → default |
| `TestMainFullMode` | `_API.json` and `.md` created, correct JSON keys, correct markdown sections, no `_NOW` files |
| `TestMainNowMode` | `_NOW.json` and `.md` created, no forecast/alerts keys in JSON, correct markdown header |
| `TestMainOutputDir` | Files written to custom dir, output dir auto-created when missing |
| `TestMainNowAndOutput` | `--now --output` combo: NOW files in custom dir, no API files, correct content |

---

## How it works

### `weather_gov_api.py` — 8 API calls

1. **Geocode** location string → lat/lon via [OSM Nominatim](https://nominatim.openstreetmap.org/)
2. **Grid point** `api.weather.gov/points/{lat},{lon}` → NWS office, forecast URLs
3. **Current conditions** nearest ASOS station observation
4. **7-day forecast** period-based narrative forecast
5. **Hourly forecast** next 24 hours
6. **Gridpoint data** apparent temperature (feels like) time series
7. **Active alerts** for the location
8. **News headlines** from the local NWS office

`--now` runs steps 1–3 and 6 only.

### No live API calls

Both test files use hardcoded fixture data and mocks — nothing touches the network.

**`tests/test_cli.py`**
- `FULL_RESULT` and `NOW_RESULT` are hardcoded dicts defined at the top of the file
- `fetch_weather` and `fetch_current` are patched with `unittest.mock.patch` to return those dicts instead of hitting the API
- `geocode` and `_get` are never called

**`tests/test_weather_gov_api.py`**
- Pure function tests (`TestCToF`, `TestFmtTime`, etc.) need no data at all — they just call the function directly
- `TestToMarkdown` and `TestToMarkdownNow` use `NOW_DATA` and `FULL_DATA` fixture dicts defined in the file
- `TestFetchCurrent` patches both `geocode` and `_get` to return controlled fake responses
- `TestGridValueAt` uses a hand-built series list

The full suite runs in ~0.1 seconds. Live API calls would belong in a separate integration test that you'd run deliberately, not as part of the regular test suite.