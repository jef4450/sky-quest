"""Offline tests for the local Sky Quest web interface."""

from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import tempfile
import unittest
from urllib.error import URLError
from urllib.request import urlopen
from unittest.mock import patch
from zoneinfo import ZoneInfo

import app


class WebFormTests(unittest.TestCase):
    def valid_form(self, activity):
        form = {
            "activity": [activity],
            "latitude": ["12.345"],
            "longitude": ["77.123"],
            "date": ["2026-10-15"],
            "start_time": ["19:00"],
            "place_label": ["Test place"],
            "output": ["card"],
            "equipment": ["naked_eye"],
            "field_of_view": ["120"],
            "window_facing": [""],
        }
        if activity == "run":
            form.update({
                "stop_name": ["Route stop"],
                "stop_latitude": ["12.346"],
                "stop_longitude": ["77.124"],
                "stop_time": ["19:30"],
            })
        return form

    def test_coordinate_and_time_validation(self):
        form = self.valid_form("walk")
        self.assertEqual(app._parse_common(form)[1:3], (12.345, 77.123))
        self.assertEqual(
            app._parse_common(form)[3],
            datetime(2026, 10, 15, 19, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        )
        for field, value in (
            ("latitude", "90.1"),
            ("longitude", "-180.1"),
            ("start_time", "25:61"),
            ("date", "not-a-date"),
        ):
            with self.subTest(field=field):
                invalid = self.valid_form("walk")
                invalid[field] = [value]
                with self.assertRaises(ValueError):
                    app._parse_common(invalid)

    def test_route_stop_validation(self):
        form = self.valid_form("run")
        self.assertEqual(
            app._parse_stops(form),
            [{
                "name": "Route stop",
                "latitude": 12.346,
                "longitude": 77.124,
                "time": "19:30",
            }],
        )
        form["stop_latitude"] = ["91"]
        with self.assertRaisesRegex(ValueError, "[Ss]top latitude"):
            app._parse_stops(form)

    def test_every_activity_maps_to_a_card_without_exposing_coordinates(self):
        for activity, expected_mode in (
            ("stay", "juvia"),
            ("walk", "lucy"),
            ("run", "natsu"),
        ):
            with self.subTest(activity=activity):
                form = self.valid_form(activity)
                form["place_label"] = ["12.345, 77.123"]
                context = {}

                def fake_print_card(lat, lon, when, *, mode, result_data, **kwargs):
                    self.assertEqual(mode, expected_mode)
                    if activity == "stay":
                        self.assertEqual(kwargs["equipment"], "naked_eye")
                        self.assertIsNone(kwargs["window_settings"]["facing"])
                    if activity == "run":
                        self.assertEqual(kwargs["stops_override"][0]["name"], "Route stop")
                    result_data["html"] = (
                        f'<main class="card {mode}">{kwargs["place_label"]}</main>'
                    )
                    result_data["facts"] = {
                        "position": {"altitude_degrees": 40},
                        "label": "12.345, 77.123",
                        "latitude": lat,
                    }
                    context["mode"] = mode

                with patch.object(app.card_engine, "print_card", side_effect=fake_print_card):
                    page = app._handle_generate(form)

                self.assertIn('class="preview"', page)
                self.assertIn(f"card {expected_mode}", page)
                self.assertIn("Facts this card is based on", page)
                self.assertNotIn("12.345", page)
                self.assertNotIn("77.123", page)
                self.assertNotIn('"latitude"', page)

    def test_javascript_audio_choice_is_rejected(self):
        form = self.valid_form("walk")
        form["output"] = ["audio"]
        with self.assertRaisesRegex(ValueError, "not available yet"):
            app._handle_generate(form)

    def test_status_bar_reports_ollama_down_without_failing(self):
        with patch("app.urlopen", side_effect=URLError("connection refused")):
            with patch.object(app, "PLANET_FILE", Path("missing-planet.bsp")):
                with patch.object(app, "ISS_FILE", Path("missing-iss.tle")):
                    status = app._status_snapshot()
                    bar = app._status_bar()
        self.assertFalse(status["ollama_reachable"])
        self.assertFalse(status["model_available"])
        self.assertIn("Ollama not reachable", bar)
        self.assertIn("Model status unavailable", bar)
        self.assertIn("Planet data missing", bar)
        self.assertIn("ISS data missing", bar)
        self.assertIn("warning", bar)

    def test_iss_tle_age_is_read_without_network(self):
        tle = "ISS (ZARYA)\n1 25544U 98067A   26285.50000000  .00000000  00000-0  00000-0 0  9999\n2 25544  51.6400  0.0000 0000000 0.0000 0.0000 15.50000000    00\n"
        with tempfile.TemporaryDirectory() as temp:
            tle_path = Path(temp) / "iss.tle"
            tle_path.write_text(tle, encoding="utf-8")
            with patch.object(app, "ISS_FILE", tle_path):
                with patch("app.urlopen", side_effect=URLError("offline")):
                    snapshot = app._status_snapshot()
        self.assertIsInstance(snapshot["iss_age_days"], int)
        self.assertGreaterEqual(snapshot["iss_age_days"], 0)

    def test_form_contains_location_button_and_audio_unavailable(self):
        page = app._form_page("stay")
        self.assertIn("Use my location", page)
        self.assertIn("Audio (not available yet)", page)
        self.assertIn('name="date" type="date"', page)
        self.assertIn('name="start_time" type="time"', page)

    def test_saved_place_coordinates_are_not_embedded_in_form_html(self):
        saved = [{
            "name": "Home",
            "latitude": 12.345,
            "longitude": 77.123,
        }]
        with patch("app._read_places", return_value=saved):
            page = app._form_page("walk")
        self.assertIn(">Home</option>", page)
        self.assertNotIn("12.345", page)
        self.assertNotIn("77.123", page)

    def test_local_http_server_serves_activity_picker(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.SkyQuestHandler)
        worker = threading.Thread(target=server.serve_forever)
        healthy_status = {
            "ollama_reachable": False,
            "model_available": False,
            "planet_data": False,
            "iss_data": False,
            "iss_age_days": None,
        }
        with patch("app._status_snapshot", return_value=healthy_status):
            worker.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=2) as response:
                    page = response.read().decode("utf-8")
                    self.assertEqual(response.status, 200)
            finally:
                server.shutdown()
                worker.join(timeout=2)
                server.server_close()
        for activity in ("Stay in one place", "Walk nearby", "Run with stops", "Ride in a car"):
            self.assertIn(activity, page)


if __name__ == "__main__":
    unittest.main()
