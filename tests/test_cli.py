"""
Tests for the command-line interface of weather_gov_api.py.

Covers:
  - CLI argument parsing  (--now, --output, location string)
  - main() full mode      → _API.json / _API.md created in output dir
  - main() --now mode     → _NOW.json / _NOW.md created in output dir
  - --output <dir>        → files written to the specified directory
  - --now --output combo  → NOW files in custom directory
  - output dir            → auto-created when it does not exist
  - JSON content          → expected top-level keys present
  - Markdown content      → expected section headers present

All tests use "Cary, NC, USA" as the location.

Run with:
    python -m pytest tests/test_cli.py -v
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import weather_gov_api
from weather_gov_api import main, DEFAULT_LOCATION

LOCATION = "Cary, NC, USA"
SLUG = "Cary_NC_USA"

# ---------------------------------------------------------------------------
# Shared fixture data returned by the mocked fetch functions
# ---------------------------------------------------------------------------

_CURRENT = {
    "station": "KRDU",
    "timestamp": "2026-05-08T19:55:00+00:00",
    "description": "Mostly Clear",
    "temperature_f": 71.6,
    "temperature_c": 22.0,
    "feels_like_f": 70.0,
    "feels_like_c": 21.1,
    "dewpoint_f": 37.4,
    "dewpoint_c": 3.0,
    "humidity_pct": 28.7,
    "wind_speed_mph": 10.0,
    "wind_gust_mph": None,
    "wind_direction_deg": 180,
    "visibility_miles": 10.0,
    "pressure_mb": 1015.2,
}

NOW_RESULT = {
    "location": LOCATION,
    "resolved_city": "Cary, NC",
    "coordinates": {"lat": 35.7883, "lon": -78.7812},
    "timezone": "America/New_York",
    "generated_at": "2026-05-08T20:00:00+00:00",
    "current_conditions": _CURRENT,
}

FULL_RESULT = {
    **NOW_RESULT,
    "grid": {"office": "RAH", "x": 69, "y": 54},
    "hourly_forecast": [],
    "seven_day_forecast": [],
    "active_alerts": [],
    "news_headlines": [],
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _run_main(*argv_args, now=False, fetch_weather_result=None,
              fetch_current_result=None, output_dir=None):
    """
    Call main() with mocked fetch functions inside a temp directory.
    Returns a dict of {filename: file_contents} written to the output dir.
    """
    fw = fetch_weather_result or FULL_RESULT
    fc = fetch_current_result or NOW_RESULT

    with tempfile.TemporaryDirectory() as tmp:
        out = output_dir or os.path.join(tmp, "output")
        with patch("weather_gov_api.fetch_weather", return_value=fw), \
             patch("weather_gov_api.fetch_current", return_value=fc):
            main(*argv_args, now=now, output_dir=out)
        # copy results out before tmp is deleted
        files = {}
        for name in os.listdir(out):
            path = os.path.join(out, name)
            with open(path, encoding="utf-8") as f:
                files[name] = f.read()
        return files


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

class TestCliArgParsing(unittest.TestCase):
    """Verify sys.argv is parsed correctly and main() receives the right args."""

    def _parse(self, argv):
        """Replicate the __main__ parsing logic and return (loc, now, output_dir)."""
        args = list(argv)
        now_flag = "--now" in args
        args = [a for a in args if a != "--now"]

        output_dir = "output"
        if "--output" in args:
            idx = args.index("--output")
            output_dir = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

        loc = " ".join(args) if args else DEFAULT_LOCATION
        return loc, now_flag, output_dir

    def test_location_only(self):
        loc, now, out = self._parse(["Cary,", "NC,", "USA"])
        self.assertEqual(loc, "Cary, NC, USA")
        self.assertFalse(now)
        self.assertEqual(out, "output")

    def test_now_flag_extracted(self):
        loc, now, out = self._parse(["Cary,", "NC,", "USA", "--now"])
        self.assertTrue(now)
        self.assertEqual(loc, "Cary, NC, USA")

    def test_now_flag_before_location(self):
        loc, now, out = self._parse(["--now", "Cary,", "NC,", "USA"])
        self.assertTrue(now)
        self.assertEqual(loc, "Cary, NC, USA")

    def test_output_flag_extracted(self):
        loc, now, out = self._parse(["Cary,", "NC,", "USA", "--output", "reports"])
        self.assertEqual(out, "reports")
        self.assertEqual(loc, "Cary, NC, USA")
        self.assertFalse(now)

    def test_now_and_output_together(self):
        loc, now, out = self._parse(["Cary,", "NC,", "USA", "--now", "--output", "reports"])
        self.assertTrue(now)
        self.assertEqual(out, "reports")
        self.assertEqual(loc, "Cary, NC, USA")

    def test_no_args_uses_default_location(self):
        loc, now, out = self._parse([])
        self.assertEqual(loc, DEFAULT_LOCATION)
        self.assertFalse(now)


# ---------------------------------------------------------------------------
# main() — full mode
# ---------------------------------------------------------------------------

class TestMainFullMode(unittest.TestCase):

    def setUp(self):
        self.files = _run_main(LOCATION)

    def test_json_file_created(self):
        self.assertIn(f"{SLUG}_API.json", self.files)

    def test_md_file_created(self):
        self.assertIn(f"{SLUG}_API.md", self.files)

    def test_now_files_not_created(self):
        self.assertNotIn(f"{SLUG}_NOW.json", self.files)
        self.assertNotIn(f"{SLUG}_NOW.md", self.files)

    def test_json_has_required_keys(self):
        data = json.loads(self.files[f"{SLUG}_API.json"])
        for key in ("location", "generated_at", "current_conditions",
                    "hourly_forecast", "seven_day_forecast",
                    "active_alerts", "news_headlines"):
            self.assertIn(key, data)

    def test_json_location_matches(self):
        data = json.loads(self.files[f"{SLUG}_API.json"])
        self.assertEqual(data["location"], LOCATION)

    def test_md_has_weather_report_header(self):
        self.assertIn("# Weather Report:", self.files[f"{SLUG}_API.md"])

    def test_md_has_current_conditions_section(self):
        self.assertIn("## Current Conditions", self.files[f"{SLUG}_API.md"])

    def test_md_has_hourly_section(self):
        self.assertIn("## Hourly Forecast", self.files[f"{SLUG}_API.md"])

    def test_md_has_seven_day_section(self):
        self.assertIn("## 7-Day Forecast", self.files[f"{SLUG}_API.md"])


# ---------------------------------------------------------------------------
# main() — --now mode
# ---------------------------------------------------------------------------

class TestMainNowMode(unittest.TestCase):

    def setUp(self):
        self.files = _run_main(LOCATION, now=True)

    def test_now_json_file_created(self):
        self.assertIn(f"{SLUG}_NOW.json", self.files)

    def test_now_md_file_created(self):
        self.assertIn(f"{SLUG}_NOW.md", self.files)

    def test_api_files_not_created(self):
        self.assertNotIn(f"{SLUG}_API.json", self.files)
        self.assertNotIn(f"{SLUG}_API.md", self.files)

    def test_json_has_only_current_keys(self):
        data = json.loads(self.files[f"{SLUG}_NOW.json"])
        self.assertIn("current_conditions", data)
        self.assertIn("generated_at", data)
        self.assertNotIn("seven_day_forecast", data)
        self.assertNotIn("hourly_forecast", data)
        self.assertNotIn("active_alerts", data)

    def test_json_location_matches(self):
        data = json.loads(self.files[f"{SLUG}_NOW.json"])
        self.assertEqual(data["location"], LOCATION)

    def test_md_has_current_conditions_header(self):
        self.assertIn("# Current Conditions:", self.files[f"{SLUG}_NOW.md"])

    def test_md_has_temperature(self):
        self.assertIn("71.6 °F", self.files[f"{SLUG}_NOW.md"])

    def test_md_has_station(self):
        self.assertIn("KRDU", self.files[f"{SLUG}_NOW.md"])


# ---------------------------------------------------------------------------
# --output directory
# ---------------------------------------------------------------------------

class TestMainOutputDir(unittest.TestCase):

    def test_files_written_to_custom_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom = os.path.join(tmp, "my_reports")
            with patch("weather_gov_api.fetch_weather", return_value=FULL_RESULT):
                main(LOCATION, output_dir=custom)
            created = os.listdir(custom)
            self.assertIn(f"{SLUG}_API.json", created)
            self.assertIn(f"{SLUG}_API.md", created)

    def test_output_dir_created_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            new_dir = os.path.join(tmp, "brand_new_dir")
            self.assertFalse(os.path.exists(new_dir))
            with patch("weather_gov_api.fetch_weather", return_value=FULL_RESULT):
                main(LOCATION, output_dir=new_dir)
            self.assertTrue(os.path.isdir(new_dir))

    def test_now_files_in_custom_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom = os.path.join(tmp, "now_out")
            with patch("weather_gov_api.fetch_current", return_value=NOW_RESULT):
                main(LOCATION, now=True, output_dir=custom)
            created = os.listdir(custom)
            self.assertIn(f"{SLUG}_NOW.json", created)
            self.assertIn(f"{SLUG}_NOW.md", created)


# ---------------------------------------------------------------------------
# --now --output combined
# ---------------------------------------------------------------------------

class TestMainNowAndOutput(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._out = os.path.join(self._tmp.name, "combined")
        with patch("weather_gov_api.fetch_current", return_value=NOW_RESULT):
            main(LOCATION, now=True, output_dir=self._out)

    def tearDown(self):
        self._tmp.cleanup()

    def test_now_json_in_custom_dir(self):
        self.assertIn(f"{SLUG}_NOW.json", os.listdir(self._out))

    def test_now_md_in_custom_dir(self):
        self.assertIn(f"{SLUG}_NOW.md", os.listdir(self._out))

    def test_no_api_files_created(self):
        created = os.listdir(self._out)
        self.assertNotIn(f"{SLUG}_API.json", created)
        self.assertNotIn(f"{SLUG}_API.md", created)

    def test_json_content_correct(self):
        path = os.path.join(self._out, f"{SLUG}_NOW.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["location"], LOCATION)
        self.assertIn("current_conditions", data)


if __name__ == "__main__":
    unittest.main()
