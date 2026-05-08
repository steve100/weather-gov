"""
Tests for weather_gov_api.py

Run with:
    python -m unittest discover tests
    python -m pytest tests          # if pytest is installed
"""

import sys
import os
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weather_gov_api import (
    location_slug,
    _c_to_f,
    _fmt_time,
    _parse_iso_duration_hours,
    _grid_value_at,
    _opt,
    to_markdown_now,
    to_markdown,
    fetch_current,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW_DATA = {
    "location": "Cary, NC, USA",
    "resolved_city": "Cary, NC",
    "coordinates": {"lat": 35.7883, "lon": -78.7812},
    "timezone": "America/New_York",
    "generated_at": "2026-05-08T20:00:00+00:00",
    "current_conditions": {
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
    },
}

FULL_DATA = {
    **NOW_DATA,
    "grid": {"office": "RAH", "x": 69, "y": 54},
    "hourly_forecast": [
        {
            "time": "2026-05-08T21:00:00-04:00",
            "temperature_f": 70,
            "feels_like_f": 70.0,
            "dewpoint_f": 37.0,
            "humidity_pct": 33.0,
            "wind_speed": "3 mph",
            "wind_direction": "S",
            "short_forecast": "Sunny",
            "precip_pct": 0,
        }
    ],
    "seven_day_forecast": [
        {
            "name": "Tonight",
            "is_daytime": False,
            "temperature": "54 °F",
            "wind_speed": "5 mph",
            "wind_direction": "S",
            "short_forecast": "Mostly Cloudy",
            "detailed_forecast": "Mostly cloudy, with a low around 54.",
            "precip_pct": 10,
            "dewpoint_f": 50.0,
            "humidity_pct": 80.0,
        }
    ],
    "active_alerts": [],
    "news_headlines": [
        {
            "title": "hurricane-prep-2026",
            "summary": "Hurricane Preparedness Week",
            "url": "https://api.weather.gov/offices/RAH/headlines/abc123",
            "issued": "2026-05-04T14:48:00+00:00",
        }
    ],
}


# ---------------------------------------------------------------------------
# location_slug
# ---------------------------------------------------------------------------

class TestLocationSlug(unittest.TestCase):

    def test_city_state_country(self):
        self.assertEqual(location_slug("Cary, NC, USA"), "Cary_NC_USA")

    def test_city_state(self):
        self.assertEqual(location_slug("Raleigh, NC"), "Raleigh_NC")

    def test_extra_spaces(self):
        self.assertEqual(location_slug("  Durham,  NC  "), "Durham_NC")

    def test_single_word(self):
        self.assertEqual(location_slug("Boston"), "Boston")


# ---------------------------------------------------------------------------
# _c_to_f
# ---------------------------------------------------------------------------

class TestCToF(unittest.TestCase):

    def test_freezing(self):
        self.assertEqual(_c_to_f(0), 32.0)

    def test_boiling(self):
        self.assertEqual(_c_to_f(100), 212.0)

    def test_body_temp(self):
        self.assertEqual(_c_to_f(37), 98.6)

    def test_negative(self):
        self.assertEqual(_c_to_f(-40), -40.0)

    def test_none_returns_none(self):
        self.assertIsNone(_c_to_f(None))

    def test_rounding(self):
        self.assertEqual(_c_to_f(22), 71.6)


# ---------------------------------------------------------------------------
# _fmt_time
# ---------------------------------------------------------------------------

class TestFmtTime(unittest.TestCase):

    def test_pm_hour(self):
        self.assertEqual(_fmt_time("2026-05-08T21:00:00-04:00"), "9 PM Fri")

    def test_noon(self):
        self.assertEqual(_fmt_time("2026-05-08T12:00:00-04:00"), "12 PM Fri")

    def test_midnight(self):
        self.assertEqual(_fmt_time("2026-05-09T00:00:00-04:00"), "12 AM Sat")

    def test_am_hour(self):
        self.assertEqual(_fmt_time("2026-05-08T09:00:00-04:00"), "9 AM Fri")


# ---------------------------------------------------------------------------
# _parse_iso_duration_hours
# ---------------------------------------------------------------------------

class TestParseIsoDurationHours(unittest.TestCase):

    def test_one_hour(self):
        self.assertEqual(_parse_iso_duration_hours("PT1H"), 1.0)

    def test_six_hours(self):
        self.assertEqual(_parse_iso_duration_hours("PT6H"), 6.0)

    def test_one_day(self):
        self.assertEqual(_parse_iso_duration_hours("P1D"), 24.0)

    def test_one_day_and_six_hours(self):
        self.assertEqual(_parse_iso_duration_hours("P1DT6H"), 30.0)

    def test_minutes(self):
        self.assertAlmostEqual(_parse_iso_duration_hours("PT30M"), 0.5)

    def test_invalid_falls_back_to_one(self):
        self.assertEqual(_parse_iso_duration_hours("INVALID"), 1.0)


# ---------------------------------------------------------------------------
# _grid_value_at
# ---------------------------------------------------------------------------

class TestGridValueAt(unittest.TestCase):

    def _series(self):
        return [
            {"validTime": "2026-05-08T18:00:00+00:00/PT1H", "value": 20.0},
            {"validTime": "2026-05-08T19:00:00+00:00/PT1H", "value": 21.0},
            {"validTime": "2026-05-08T20:00:00+00:00/PT1H", "value": 22.0},
            {"validTime": "2026-05-08T21:00:00+00:00/PT3H", "value": 21.5},
        ]

    def test_matches_exact_start(self):
        dt = datetime(2026, 5, 8, 20, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(_grid_value_at(self._series(), dt), 22.0)

    def test_matches_within_interval(self):
        dt = datetime(2026, 5, 8, 22, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(_grid_value_at(self._series(), dt), 21.5)

    def test_before_series_returns_none(self):
        dt = datetime(2026, 5, 8, 17, 0, 0, tzinfo=timezone.utc)
        self.assertIsNone(_grid_value_at(self._series(), dt))

    def test_empty_series_returns_none(self):
        self.assertIsNone(_grid_value_at([], datetime.now(timezone.utc)))


# ---------------------------------------------------------------------------
# _opt
# ---------------------------------------------------------------------------

class TestOpt(unittest.TestCase):

    def test_with_value(self):
        self.assertEqual(_opt(10.5, " mph"), "10.5 mph")

    def test_none_returns_default(self):
        self.assertEqual(_opt(None, " mph"), "N/A")

    def test_custom_default(self):
        self.assertEqual(_opt(None, suffix="%", default="--"), "--")

    def test_zero_is_not_none(self):
        self.assertEqual(_opt(0, "%"), "0%")


# ---------------------------------------------------------------------------
# to_markdown_now
# ---------------------------------------------------------------------------

class TestToMarkdownNow(unittest.TestCase):

    def setUp(self):
        self.md = to_markdown_now(NOW_DATA)

    def test_has_location_header(self):
        self.assertIn("# Current Conditions: Cary, NC, USA", self.md)

    def test_resolved_city_appended(self):
        self.assertIn("(Cary, NC)", self.md)

    def test_generated_at_present(self):
        self.assertIn("2026-05-08T20:00:00+00:00", self.md)

    def test_temperature_present(self):
        self.assertIn("71.6 °F", self.md)

    def test_feels_like_present(self):
        self.assertIn("70.0 °F", self.md)

    def test_station_present(self):
        self.assertIn("KRDU", self.md)

    def test_wind_gust_na_when_none(self):
        self.assertIn("| Wind Gusts | N/A |", self.md)


# ---------------------------------------------------------------------------
# to_markdown (full report)
# ---------------------------------------------------------------------------

class TestToMarkdown(unittest.TestCase):

    def setUp(self):
        self.md = to_markdown(FULL_DATA)

    def test_has_weather_report_header(self):
        self.assertIn("# Weather Report: Cary, NC, USA", self.md)

    def test_hourly_section_present(self):
        self.assertIn("## Hourly Forecast (Next 24 Hours)", self.md)

    def test_hourly_row_present(self):
        self.assertIn("Sunny", self.md)

    def test_seven_day_section_present(self):
        self.assertIn("## 7-Day Forecast", self.md)

    def test_forecast_period_present(self):
        self.assertIn("### Tonight", self.md)

    def test_precip_pct_in_forecast(self):
        self.assertIn("Precip: 10%", self.md)

    def test_no_active_alerts(self):
        self.assertIn("No active alerts.", self.md)

    def test_news_headline_present(self):
        self.assertIn("Hurricane Preparedness Week", self.md)


# ---------------------------------------------------------------------------
# fetch_current (mocked)
# ---------------------------------------------------------------------------

class TestFetchCurrent(unittest.TestCase):

    def _make_obs_props(self):
        def obs_val(v):
            return {"value": v}
        return {
            "timestamp": "2026-05-08T20:00:00+00:00",
            "textDescription": "Clear",
            "temperature": obs_val(22.0),
            "windSpeed": obs_val(4.47),
            "windGust": obs_val(None),
            "dewpoint": obs_val(3.0),
            "relativeHumidity": obs_val(30.0),
            "visibility": obs_val(16090.0),
            "barometricPressure": obs_val(101520.0),
            "windDirection": obs_val(180),
        }

    @patch("weather_gov_api.geocode", return_value=(35.7883, -78.7812))
    @patch("weather_gov_api._get")
    def test_returns_current_conditions_key(self, mock_get, _mock_geocode):
        mock_get.side_effect = [
            # /points
            {"properties": {
                "forecast": "https://x/forecast",
                "forecastHourly": "https://x/hourly",
                "observationStations": "https://x/stations",
                "cwa": "RAH", "gridX": 69, "gridY": 54,
                "timeZone": "America/New_York",
                "relativeLocation": {"properties": {"city": "Cary", "state": "NC"}},
            }},
            # /stations
            {"features": [{"properties": {"stationIdentifier": "KRDU"}}]},
            # /observations/latest
            {"properties": self._make_obs_props()},
            # /gridpoints (apparent temperature)
            {"properties": {"apparentTemperature": {"values": [
                {"validTime": "2026-01-01T00:00:00+00:00/P1D", "value": 21.0}
            ]}}},
        ]

        result = fetch_current("Cary, NC, USA")

        self.assertIn("current_conditions", result)
        self.assertIn("generated_at", result)
        self.assertNotIn("seven_day_forecast", result)
        self.assertNotIn("hourly_forecast", result)

    @patch("weather_gov_api.geocode", return_value=(35.7883, -78.7812))
    @patch("weather_gov_api._get")
    def test_temperature_converted_correctly(self, mock_get, _mock_geocode):
        mock_get.side_effect = [
            {"properties": {
                "forecast": "https://x/forecast",
                "forecastHourly": "https://x/hourly",
                "observationStations": "https://x/stations",
                "cwa": "RAH", "gridX": 69, "gridY": 54,
                "timeZone": "America/New_York",
                "relativeLocation": {"properties": {"city": "Cary", "state": "NC"}},
            }},
            {"features": [{"properties": {"stationIdentifier": "KRDU"}}]},
            {"properties": self._make_obs_props()},
            {"properties": {"apparentTemperature": {"values": []}}},
        ]

        result = fetch_current("Cary, NC, USA")
        self.assertEqual(result["current_conditions"]["temperature_f"], 71.6)
        self.assertEqual(result["current_conditions"]["temperature_c"], 22.0)

    @patch("weather_gov_api.geocode", side_effect=ValueError("Could not geocode"))
    def test_invalid_location_raises(self, _mock_geocode):
        with self.assertRaises(ValueError):
            fetch_current("ZZZNOTAPLACE")


if __name__ == "__main__":
    unittest.main()
