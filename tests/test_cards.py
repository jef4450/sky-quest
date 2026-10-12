"""Offline tests for card rendering, modes, and per-stop sky calculations."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import call, patch
from zoneinfo import ZoneInfo

import main
import scorer
import stars
import config
import deep_sky_targets
from constellation_guides import applicable_guides
from html_cards import NO_ISS_MESSAGE, render_html_card
from sky import _summarize_pass, height_word, load_sky_data


TZ = ZoneInfo("Asia/Kolkata")
START = datetime(2026, 10, 15, 20, 0, tzinfo=TZ)
END = START + timedelta(hours=1)


def position(altitude, direction="east", height="halfway up"):
    azimuths = {
        "north": 0,
        "north-east": 45,
        "east": 90,
        "south-east": 135,
        "south": 180,
        "south-west": 225,
        "west": 270,
        "north-west": 315,
    }
    return {
        "altitude_degrees": altitude,
        "azimuth_degrees": azimuths[direction],
        "direction": direction,
        "height": height,
        "above_horizon": altitude > 0,
    }


def sky_facts():
    return {
        "dark_start": START.isoformat(),
        "moon_illumination": 0.3,
        "moon_phase": "waxing crescent",
        "moonrise": "8:30 PM",
        "moonset": "10:00 PM",
        "sunset": "6:00 PM",
        "dark_time": "7:00 PM",
        "positions": {
            "Moon": position(25, "south-west", "low"),
            "Jupiter": position(70, "east", "high"),
            "Saturn": position(35, "south", "halfway up"),
        },
    }


def best_window():
    return {
        "window_start": START,
        "window_end": END,
        "start": START,
        "end": END,
        "total_score": 12,
        "reasons": ["Jupiter is high around 8:30 PM"],
        "positions": sky_facts()["positions"],
        "message": "",
    }


def star_facts():
    names = set(stars.BRIGHT_STARS) | set(stars.GUIDE_ANCHOR_STARS)
    result = {}
    for name in names:
        altitude = 35 if name == "Polaris" else 10
        result[name] = position(altitude, "north", "high" if altitude > 15 else "low")
    return result


class HtmlCardTests(unittest.TestCase):
    def data(self):
        return {
            "title": "Test card",
            "date": "Thursday, October 15, 2026",
            "place_label": "My terrace <test>",
            "window_text": "8:00 PM to 9:00 PM",
            "iss_passes": [],
            "telescope_targets": [],
            "intro": "A calm introduction.",
            "checklist": ["Jupiter: east, high, above the horizon"],
            "targets": [],
            "stops": [],
            "timeline": [],
            "route_text": "Route: 8:00 PM to 9:00 PM",
            "window_facing": None,
            "stops_label": "Configured route stops",
            "polaris": {
                "text": "Polaris is low from here: you need a clear north horizon.",
                "visible": True,
                "checkable": False,
            },
            "stars": [],
            "guides": [],
        }

    def test_dynamic_text_is_escaped(self):
        html = render_html_card("lucy", self.data())
        self.assertIn("My terrace &lt;test&gt;", html)
        self.assertNotIn("My terrace <test>", html)
        self.assertIn("&lt;", html)

    def test_coordinate_pairs_in_dynamic_text_are_redacted(self):
        data = self.data()
        data["place_label"] = "12.3456, 77.1234"
        html = render_html_card("lucy", data)
        self.assertNotIn("12.3456", html)
        self.assertNotIn("77.1234", html)
        self.assertIn("[location omitted]", html)

    def test_every_mode_shows_same_exact_no_iss_message(self):
        for mode in ("lucy", "juvia", "natsu"):
            with self.subTest(mode=mode):
                html = render_html_card(mode, self.data())
                self.assertIn(NO_ISS_MESSAGE, html)
                self.assertEqual(html.count('class="iss"'), 1)

    def test_every_mode_has_print_style_and_empty_checkbox(self):
        for mode in ("lucy", "juvia", "natsu"):
            data = self.data()
            if mode == "juvia":
                data["timeline"] = [
                    {
                        "time": "8:00 PM",
                        "items": [
                            {
                                "text": "Jupiter: east, high",
                                "checkable": True,
                                "note": "a steady bright dot; planets do not twinkle",
                            }
                        ],
                        "empty": False,
                        "iss_passes": [],
                    }
                ]
            if mode == "natsu":
                data["stops"] = [
                    {
                        "number": 1,
                        "name": "Example",
                        "date": "",
                        "time": "8:00 PM",
                        "target": {
                            "object": "Jupiter",
                            "direction": "east",
                            "height": "high",
                        },
                        "status": "",
                    }
                ]
            html = render_html_card(mode, data)
            self.assertIn("@page { size: A4; margin: 15mm; }", html)
            self.assertIn('class="box"', html)
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)

    def test_physical_print_units_rows_and_mode_sizing(self):
        lucy = render_html_card("lucy", self.data())
        juvia = render_html_card("juvia", self.data())
        natsu = render_html_card("natsu", self.data())
        self.assertIn("font: 15.5pt/1.35", lucy)
        self.assertIn("font-size: 24pt", lucy)
        self.assertIn("font-size: 36pt", lucy)
        self.assertIn("width: 12mm; height: 12mm", lucy)
        self.assertIn("break-inside: avoid", lucy)
        self.assertIn("font-size: 13.5pt", juvia)
        self.assertIn("font-size: 16pt; font-weight: 700", juvia)
        self.assertIn("height: 30mm", juvia)
        self.assertIn("width: 105mm", natsu)
        self.assertNotRegex(lucy, r"\b\d+(?:\.\d+)?(?:vh|vw|px)\b")
        self.assertIn("print-color-adjust: exact", lucy)
        self.assertIn("-webkit-print-color-adjust: exact", lucy)

    def test_juvia_renders_timeline_and_naked_eye_notes(self):
        data = self.data()
        data["window_facing"] = "east"
        data["timeline"] = [
            {
                "time": "8:00 PM",
                "items": [
                    {
                        "text": "Jupiter: not in your window",
                        "checkable": False,
                    },
                    {
                        "text": "Moon: west, low",
                        "checkable": True,
                        "note": "look for its dark patches",
                    },
                ],
                "empty": False,
                "iss_passes": [],
            }
        ]
        html = render_html_card("juvia", data)
        self.assertIn("Sky Quest - Test card", html)
        self.assertIn("Window facing: east", html)
        self.assertIn("Estimated viewing times", html)
        self.assertIn("Jupiter: not in your window", html)
        self.assertIn("Each listed target passed the local", html)
        outside = html.split("Jupiter: not in your window", 1)[1].split("</li>", 1)[0]
        self.assertNotIn('class="box"', outside)
        self.assertIn("class=\"box\"", html)
        self.assertIn("height: 30mm", html)

    def test_natsu_safety_line_is_exact(self):
        html = render_html_card("natsu", self.data())
        self.assertIn("Stop moving before you look up.", html)

    def test_natsu_header_uses_route_span_not_global_window(self):
        html = render_html_card("natsu", self.data())
        self.assertIn("Route: 8:00 PM to 9:00 PM", html)
        self.assertNotIn("Best viewing window", html)

    def test_natsu_status_rows_have_no_checkbox_and_escape_content(self):
        data = self.data()
        data["stops"] = [
            {
                "number": 1,
                "name": "Park <script>",
                "date": "Oct 16",
                "time": "12:15 AM",
                "target": None,
                "status": "sky not dark yet at this stop",
            },
            {
                "number": 2,
                "name": "Dark but empty",
                "date": "",
                "time": "1:00 AM",
                "target": None,
                "status": "nothing above the horizon at this stop",
            },
        ]
        html = render_html_card("natsu", data)
        self.assertIn("Oct 16, 12:15 AM local", html)
        self.assertIn("sky not dark yet at this stop", html)
        self.assertIn("Park &lt;script&gt;", html)
        for stop_number in ("Stop 1 -", "Stop 2 -"):
            stop_row = html.split(stop_number, 1)[1].split("</li>", 1)[0]
            self.assertNotIn('class="box"', stop_row)
        self.assertIn("nothing above the horizon at this stop", html)

    def test_lucy_does_not_add_boxes_for_below_horizon_items(self):
        data = self.data()
        data["checklist"] = [
            {"text": "Moon: north, low, below the horizon", "visible": False, "checkable": False},
            {"text": "Jupiter: east, high, above the horizon", "visible": True, "checkable": True},
        ]
        data["polaris"] = {
            "text": "Polaris is not visible from this latitude",
            "visible": False,
            "checkable": False,
        }
        data["stars"] = [
            {
                "name": "Sirius",
                "direction": "south-east",
                "height": "low",
                "above_horizon": True,
            }
        ]
        html = render_html_card("lucy", data)
        moon_row = html.split("Moon:", 1)[1].split("</li>", 1)[0]
        polaris_row = html.split("Polaris is not visible", 1)[1].split("</li>", 1)[0]
        self.assertNotIn('class="box"', moon_row)
        self.assertNotIn('class="box"', polaris_row)
        self.assertIn("Sirius: south-east, low", html)
        data["polaris"] = {
            "text": "Polaris is low from here: you need a clear north horizon.",
            "visible": True,
            "checkable": False,
        }
        low_row = render_html_card("lucy", data).split(
            "Polaris is low from here", 1
        )[1].split("</li>", 1)[0]
        self.assertNotIn('class="box"', low_row)

    def test_lucy_star_and_guide_sections_are_escaped(self):
        data = self.data()
        data["stars"] = [
            {
                "name": "Vega <unsafe>",
                "direction": "east",
                "height": "high",
                "above_horizon": True,
            }
        ]
        data["guides"] = [{"name": "Orion", "text": "Orion's belt is <visible>."}]
        html = render_html_card("lucy", data)
        self.assertIn("Vega &lt;unsafe&gt;", html)
        self.assertIn("Orion&#x27;s belt is &lt;visible&gt;.", html)
        self.assertNotIn("Vega <unsafe>", html)


class ModeAndAstronomyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp.name) / "cards"
        self.patchers = [
            patch("main.load_sky_data", return_value=("ephemeris", "timescale")),
            patch("main.get_sky", return_value=sky_facts()),
            patch("main.find_iss_passes", return_value=[]),
            patch("main.score_night", return_value=best_window()),
            patch("main.narrate", return_value="A grounded introduction."),
            patch("main.is_dark_at", return_value=True),
            patch("main.get_star_positions", return_value=star_facts()),
            patch("main.moon_illumination_at", return_value=0.1),
            patch("main.get_telescope_target_positions", return_value={}),
        ]
        self.mocks = [item.start() for item in self.patchers]
        self.addCleanup(self.temp.cleanup)
        for item in self.patchers:
            self.addCleanup(item.stop)

    def test_default_mode_is_lucy_and_all_modes_accept_demo(self):
        with patch("main.print_card") as print_card:
            self.assertEqual(main.main(["--demo"]), 0)
            self.assertEqual(print_card.call_args.kwargs["mode"], "lucy")
            self.assertTrue(print_card.call_args.kwargs["demo"])
            for mode in ("lucy", "juvia", "natsu"):
                self.assertEqual(main.main(["--demo", "--mode", mode]), 0)
                self.assertEqual(print_card.call_args.kwargs["mode"], mode)
                self.assertTrue(print_card.call_args.kwargs["demo"])

    def test_modes_render_cards_and_use_their_grounded_personas(self):
        with patch("main.get_positions", return_value=sky_facts()["positions"]):
            for mode, persona, count in (
                ("lucy", "calm", 2),
                ("natsu", "coach", 1),
            ):
                path = main.print_card(
                    12.0,
                    77.0,
                    datetime(2026, 10, 15, 18, 0, tzinfo=TZ),
                    mode=mode,
                    demo=True,
                    output_dir=self.output_dir,
                )
                self.assertTrue(path.exists())
                self.assertIn(f"<main class=\"card {mode}\">", path.read_text(encoding="utf-8"))
                self.assertIn(NO_ISS_MESSAGE, path.read_text(encoding="utf-8"))
                self.assertNotIn("12.0", path.read_text(encoding="utf-8"))
                self.assertNotIn("77.0", path.read_text(encoding="utf-8"))
                self.assertNotRegex(
                    path.read_text(encoding="utf-8"),
                    r"\b\d{1,3}\.\d+\s*[,/]\s*\d{1,3}\.\d+\b",
                )
                self.assertEqual(self.mocks[4].call_args.args[1], persona)
                self.assertEqual(self.mocks[4].call_args.kwargs["sentence_count"], count)
                self.assertTrue(
                    self.mocks[4].call_args.kwargs["validate_sentence_count"]
                )
                self.assertTrue(self.mocks[4].call_args.kwargs["deterministic"])
        calls_before_juvia = self.mocks[4].call_count
        with patch("main.get_positions", return_value=sky_facts()["positions"]):
            main.print_card(
                12.0,
                77.0,
                datetime(2026, 10, 15, 18, 0, tzinfo=TZ),
                mode="juvia",
                demo=True,
                output_dir=self.output_dir,
            )
        self.assertEqual(self.mocks[4].call_count, calls_before_juvia)
        juvia_html = (self.output_dir / "juvia-2026-10-15.html").read_text(encoding="utf-8")
        self.assertNotIn("this is juvias", juvia_html.lower())

    def test_natsu_schedule_has_each_stop_once_and_no_stop_summary(self):
        with patch("main.get_positions", return_value=sky_facts()["positions"]):
            path = main.print_card(
                12.0,
                77.0,
                datetime(2026, 10, 15, 18, 0, tzinfo=TZ),
                mode="natsu",
                demo=True,
                output_dir=self.output_dir,
            )
        html = path.read_text(encoding="utf-8")
        for stop_number in ("Stop 1 -", "Stop 2 -", "Stop 3 -"):
            self.assertEqual(html.count(stop_number), 1)
        self.assertEqual(html.count("Fictional Garden Gate"), 1)
        self.assertEqual(html.count("Fictional Quiet Corner"), 1)
        self.assertEqual(html.count("Fictional Open Path"), 1)
        self.assertNotIn("Best viewing window", html)
        self.assertIn("Demo placeholders - fictional sample stops", html)
        self.assertIn(
            "Route (Asia/Kolkata): Oct 15, 2026, 7:30 PM to 9:00 PM",
            html,
        )
        self.assertIn("Oct 15, 2026, 7:30 PM local", html)
        self.assertIn("Oct 15, 2026, 8:15 PM local", html)
        self.assertIn("Oct 15, 2026, 9:00 PM local", html)
        self.assertIn("Stop moving before you look up.", html)

    def test_natsu_does_not_calculate_or_pass_a_global_best_window(self):
        with patch("main.get_sky") as get_sky:
            with patch("main.score_night") as score_night:
                with patch("main.get_star_positions", return_value=star_facts()):
                    with patch("main.is_dark_at", return_value=True):
                        with patch("main.get_positions", return_value=sky_facts()["positions"]):
                            with patch("main.find_iss_passes", return_value=[]):
                                with patch("main.narrate", return_value="A grounded introduction.") as narrate_call:
                                    main.print_card(
                                        12.0,
                                        77.0,
                                        datetime(2026, 10, 15, 18, 0, tzinfo=TZ),
                                        mode="natsu",
                                        demo=True,
                                        output_dir=self.output_dir,
                                    )
        get_sky.assert_not_called()
        score_night.assert_not_called()
        facts = narrate_call.call_args.args[0]
        self.assertNotIn("best_window", facts)
        self.assertNotIn("positions", facts)

    def test_juvia_full_sky_includes_above_horizon_targets(self):
        dark_start = START.replace(hour=20)
        positions = {
            "Moon": position(5, "west", "low"),
            "Jupiter": position(30, "east", "halfway up"),
            "Saturn": position(-1, "south", "low"),
        }
        stars_at_time = star_facts()
        stars_at_time["Polaris"] = position(35, "north", "high")
        with patch("main.get_positions", return_value=positions) as get_positions:
            with patch("main.get_star_positions", return_value=stars_at_time):
                timeline, facts = main._juvia_timeline(
                    dark_start, "eph", "ts", 1, 2, [], None, 120, 10
                )
        self.assertEqual(get_positions.call_count, 4)
        self.assertIn(
            "Moon: west, low",
            [item["text"] for item in timeline[0]["items"]],
        )
        self.assertIn("Jupiter", facts["timeline"][0]["positions"])
        self.assertNotIn("Saturn", facts["timeline"][0]["positions"])
        self.assertNotIn("best_window", facts)

    def test_juvia_facing_window_filters_targets_and_full_sky_does_not(self):
        dark_start = START.replace(hour=20)
        positions = {
            "Moon": position(25, "west", "low"),
            "Jupiter": position(30, "east", "halfway up"),
            "Saturn": position(40, "south", "halfway up"),
        }
        stars_at_time = {
            name: position(-5, "north", "low")
            for name in stars.STAR_CATALOG
        }
        stars_at_time["Polaris"] = position(-5, "north", "low")
        with patch("main.get_positions", return_value=positions):
            with patch("main.get_star_positions", return_value=stars_at_time):
                facing_timeline, facts = main._juvia_timeline(
                    dark_start, "eph", "ts", 1, 2, [], "east", 120, 10
                )
                full_timeline, _ = main._juvia_timeline(
                    dark_start, "eph", "ts", 1, 2, [], None, 120, 10
                )
        first_row = facing_timeline[0]
        items = {item["text"]: item for item in first_row["items"]}
        self.assertTrue(items["Jupiter: east, halfway up"]["checkable"])
        self.assertFalse(items["Moon: not in your window"]["checkable"])
        self.assertFalse(items["Saturn: not in your window"]["checkable"])
        self.assertNotIn("Moon", facts["timeline"][0]["positions"])
        self.assertIn(
            "Moon: west, low",
            [item["text"] for item in full_timeline[0]["items"]],
        )

    def test_juvia_window_minimum_altitude_is_enforced(self):
        near_horizon = position(8, "east", "low")
        self.assertFalse(main._juvia_in_window(near_horizon, "east", 120, 10))
        self.assertTrue(main._juvia_in_window(near_horizon, "east", 120, 5))
        self.assertTrue(main._juvia_in_window(near_horizon, None, 120, 10))

    def test_telescope_catalog_covers_requested_target_classes(self):
        self.assertEqual(
            {target["kind"] for target in deep_sky_targets.TARGET_CATALOG},
            {
                "double star",
                "open cluster",
                "globular cluster",
                "nebula",
                "galaxy",
            },
        )

    def test_telescope_candidates_require_darkness_altitude_and_moon_conditions(self):
        moon = position(40, "east", "halfway up")
        target = {
            **position(45, "east", "halfway up"),
            "kind": "galaxy",
        }
        self.assertFalse(
            deep_sky_targets.passes_telescope_conditions(target, moon, 0.8, True)
        )
        self.assertFalse(
            deep_sky_targets.passes_telescope_conditions(target, moon, 0.1, True)
        )
        far_target = {**target, **position(45, "west", "halfway up")}
        self.assertTrue(
            deep_sky_targets.passes_telescope_conditions(far_target, moon, 0.1, True)
        )
        self.assertFalse(
            deep_sky_targets.passes_telescope_conditions(far_target, moon, 0.1, False)
        )
        low_target = {**far_target, **position(12, "west", "low")}
        self.assertFalse(
            deep_sky_targets.passes_telescope_conditions(low_target, moon, 0.1, True)
        )
        double_star = {**far_target, "kind": "double star"}
        self.assertTrue(
            deep_sky_targets.passes_telescope_conditions(double_star, moon, 0.8, True)
        )

    def test_juvia_timeline_includes_only_checked_catalog_candidates(self):
        target_positions = {}
        for index, target in enumerate(deep_sky_targets.TARGET_CATALOG):
            target_positions[target["catalog"]] = {
                **target,
                **position(30 + index, "east", "halfway up"),
            }
        target_positions["M 51"] = {
            **target_positions["M 51"],
            **position(-5, "east", "below the horizon"),
        }
        moon = position(-10, "north", "below the horizon")
        planets = {
            "Moon": moon,
            "Jupiter": position(-3, "west", "below the horizon"),
            "Saturn": position(-5, "south", "below the horizon"),
        }
        with patch("main.get_positions", return_value=planets):
            with patch("main.get_star_positions", return_value={
                name: position(-5, "south", "below the horizon")
                for name in stars.STAR_CATALOG
            }):
                with patch(
                    "main.get_telescope_target_positions",
                    return_value=target_positions,
                ):
                    with patch("main.is_dark_at", return_value=True):
                        with patch("main.moon_illumination_at", return_value=0.1):
                            timeline, facts = main._juvia_timeline(
                                START, "eph", "ts", 20, 0, [], None, 120, 10
                            )
        candidates = timeline[0]["telescope_targets"]
        self.assertEqual(
            {item["kind"] for item in candidates},
            {
                "double star",
                "open cluster",
                "globular cluster",
                "nebula",
                "galaxy",
            },
        )
        self.assertNotIn(
            "M 51",
            [item["catalog"] for item in candidates],
        )
        self.assertEqual(len(candidates), 5)
        self.assertEqual(len(facts["timeline"][0]["telescope_targets"]), 5)

    def test_juvia_excludes_deep_sky_targets_under_a_bright_moon(self):
        targets = {
            target["catalog"]: {
                **target,
                **position(45, "east", "halfway up"),
            }
            for target in deep_sky_targets.TARGET_CATALOG
        }
        planets = {
            "Moon": position(40, "east", "halfway up"),
            "Jupiter": position(-5, "west", "below the horizon"),
            "Saturn": position(-5, "west", "below the horizon"),
        }
        with patch("main.get_positions", return_value=planets):
            with patch("main.get_star_positions", return_value={
                name: position(-5, "south", "below the horizon")
                for name in stars.STAR_CATALOG
            }):
                with patch("main.get_telescope_target_positions", return_value=targets):
                    with patch("main.is_dark_at", return_value=True):
                        with patch("main.moon_illumination_at", return_value=0.9):
                            timeline, _ = main._juvia_timeline(
                                START, "eph", "ts", 20, 0, [], None, 120, 10
                            )
        self.assertEqual(
            [item["kind"] for item in timeline[0]["telescope_targets"]],
            ["double star"],
        )

    def test_lucy_below_horizon_has_no_low_height_description(self):
        self.assertEqual(height_word(-0.1), "below the horizon")
        line = main._object_line("Jupiter", position(-10, "east", "low"))
        self.assertEqual(line["text"], "Jupiter: below the horizon")
        self.assertFalse(line["checkable"])

    def test_best_window_scoring_selects_a_contiguous_maximum_score_window(self):
        below = {
            "Moon": position(-5, "west", "below the horizon"),
            "Jupiter": position(0, "east", "below the horizon"),
            "Saturn": position(-5, "south", "below the horizon"),
        }
        high = {
            "Moon": position(-5, "west", "below the horizon"),
            "Jupiter": position(80, "east", "high"),
            "Saturn": position(-5, "south", "below the horizon"),
        }
        with patch(
            "scorer.get_positions",
            side_effect=[below] * 8 + [high] * 4,
        ) as get_positions:
            result = scorer.score_night(
                1.0, 2.0, START, 0.0, [], "ephemeris", "timescale"
            )
        self.assertEqual(get_positions.call_count, 12)
        self.assertEqual(result["window_start"], START + timedelta(hours=2))
        self.assertEqual(result["window_end"], START + timedelta(hours=3))
        self.assertEqual(
            result["window_end"] - result["window_start"],
            timedelta(minutes=config.BEST_WINDOW_MINUTES),
        )
        self.assertTrue(main._valid_best_window(result))

    def test_best_window_validation_rejects_inconsistent_visibility_and_duration(self):
        invalid_visibility = best_window()
        invalid_visibility["positions"]["Jupiter"] = position(-1, "east", "low")
        self.assertFalse(main._valid_best_window(invalid_visibility))
        invalid_duration = best_window()
        invalid_duration["window_end"] += timedelta(minutes=15)
        self.assertFalse(main._valid_best_window(invalid_duration))

    def test_iss_pass_presentation_labels_full_local_date_and_time(self):
        summary = _summarize_pass(
            [
                (START, True, 20.0, 270.0),
                (START + timedelta(minutes=1), True, 30.0, 90.0),
            ]
        )
        self.assertEqual(summary["local_date_time"], "Oct 15, 2026 at 8:00 PM")
        pass_record = {
            **summary,
        }
        html = render_html_card(
            "lucy",
            {**HtmlCardTests().data(), "iss_passes": [pass_record]},
        )
        self.assertIn("Visible ISS pass (local time)", html)
        self.assertIn("Oct 15, 2026 at 8:00 PM", html)

    def test_juvia_empty_rows_iss_assignment_and_row_cap(self):
        dark_start = START.replace(hour=17)
        dark_start = dark_start.replace(minute=0)
        hidden = {
            "Moon": position(-2, "east", "low"),
            "Jupiter": position(-1, "east", "low"),
            "Saturn": position(-5, "west", "low"),
        }
        hidden_stars = {
            name: position(-1, "east", "low")
            for name in stars.STAR_CATALOG
        }
        visible_pass = {
            "start": "Oct 15, 8:20 PM",
            "start_datetime": START.isoformat(),
            "appears_from": "west",
            "disappears_toward": "east",
        }
        with patch("main.get_positions", return_value=hidden):
            with patch("main.get_star_positions", return_value=hidden_stars):
                timeline, _ = main._juvia_timeline(
                    dark_start, "eph", "ts", 1, 2, [visible_pass], None, 120, 10
                )
        self.assertLessEqual(len(timeline), main.MAX_JUVIA_ROWS)
        self.assertTrue(timeline[0]["empty"])
        self.assertEqual(
            [row["time"] for row in timeline],
            ["5:00 PM", "6:00 PM", "7:00 PM", "8:00 PM", "9:00 PM"],
        )
        self.assertEqual(len(timeline[3]["iss_passes"]), 1)
        data = HtmlCardTests().data()
        data["timeline"] = timeline[:1]
        data["timeline"][0]["iss_passes"] = []
        html = render_html_card("juvia", data)
        self.assertIn("nothing in your window at this time", html)
        self.assertIn(NO_ISS_MESSAGE, html)

    def test_juvia_iss_appears_only_in_the_timeline_row(self):
        data = HtmlCardTests().data()
        data["timeline"] = [
            {
                "time": "8:00 PM",
                "items": [],
                "empty": True,
                "iss_passes": [
                    {
                        "start": "Oct 15, 8:20 PM",
                        "local_date_time": "Oct 15, 2026 at 8:20 PM",
                        "appears_from": "west",
                        "disappears_toward": "east",
                    }
                ],
            }
        ]
        data["iss_passes"] = data["timeline"][0]["iss_passes"]
        html = render_html_card("juvia", data)
        self.assertIn(
            "ISS (local time): Oct 15, 2026 at 8:20 PM; from west toward east",
            html,
        )
        self.assertNotIn(NO_ISS_MESSAGE, html)
        self.assertEqual(
            html.count("ISS (local time): Oct 15, 2026 at 8:20 PM; from west toward east"),
            1,
        )

    def test_juvia_real_polaris_rules_at_three_latitudes(self):
        dark_start = START
        hidden_planets = {
            "Moon": position(-2, "east", "low"),
            "Jupiter": position(-2, "east", "low"),
            "Saturn": position(-2, "east", "low"),
        }
        for latitude, polaris, expected in (
            (50.0, position(35, "north", "high"), "Polaris: north, high"),
            (
                10.0,
                position(5, "north", "low"),
                "Polaris is low from here: you need a clear north horizon.",
            ),
            (
                -35.0,
                position(-20, "north", "low"),
                "Polaris is not visible from this latitude",
            ),
        ):
            with self.subTest(latitude=latitude):
                star_positions = {
                    name: position(-20, "south", "low")
                    for name in stars.STAR_CATALOG
                }
                star_positions["Polaris"] = polaris
                with patch("main.get_positions", return_value=hidden_planets):
                    with patch("main.get_star_positions", return_value=star_positions):
                        timeline, _ = main._juvia_timeline(
                            dark_start, "ephemeris", "timescale", latitude,
                            0.0, [], None, 120, 10,
                        )
                self.assertIn(
                    expected,
                    [item["text"] for item in timeline[0]["items"]],
                )

    def test_juvia_window_settings_are_validated(self):
        invalid_settings = (
            ("WINDOW_FACING", "up"),
            ("WINDOW_FIELD_OF_VIEW", 0),
            ("WINDOW_FIELD_OF_VIEW", float("inf")),
            ("WINDOW_MIN_ALTITUDE", 91),
        )
        for setting, value in invalid_settings:
            with self.subTest(setting=setting, value=value):
                with patch.object(config, setting, value):
                    with self.assertRaises(ValueError):
                        config._validate_window_settings()

    def test_juvia_narration_only_receives_objects_in_its_window(self):
        positions = {
            "Moon": position(20, "west", "halfway up"),
            "Jupiter": position(35, "east", "high"),
            "Saturn": position(-2, "south", "low"),
        }
        star_positions = {
            name: position(-5, "north", "low")
            for name in stars.STAR_CATALOG
        }
        star_positions["Sirius"] = position(25, "east", "halfway up")
        with patch.object(config, "WINDOW_FACING", "east"):
            with patch("main.get_positions", return_value=positions):
                with patch("main.get_star_positions", return_value=star_positions):
                    main.print_card(
                        12.0,
                        77.0,
                        START,
                        mode="juvia",
                        output_dir=self.output_dir,
                    )
        self.mocks[4].assert_not_called()
        html = (self.output_dir / "juvia-2026-10-15.html").read_text(encoding="utf-8")
        self.assertIn("Telescope candidates pass the altitude", html)
        self.assertNotIn("this is juvias", html.lower())

    def test_invalid_stops_are_skipped_without_printing_coordinates(self):
        source = Path(self.temp.name) / "stops.local.json"
        private_coordinate = 91.234567
        source.write_text(
            json.dumps(
                [
                    {"name": "Valid", "latitude": 1.0, "longitude": 2.0, "time": "19:30"},
                    {"name": "Invalid", "latitude": private_coordinate, "longitude": 2.0, "time": "19:30"},
                ]
            ),
            encoding="utf-8",
        )
        with patch.object(main, "PROJECT_DIR", Path(self.temp.name)):
            with patch("builtins.print") as printed:
                stops = main._load_stops(False)
        self.assertEqual(len(stops), 1)
        self.assertNotIn(str(private_coordinate), str(printed.call_args))
        self.assertIn("Skipping invalid stop entry 2", printed.call_args.args[0])

    def test_natsu_uses_each_stop_location_time_and_highest_visible_target(self):
        stops = [
            {"name": "First", "latitude": 1.1, "longitude": 2.2, "time": "19:30"},
            {"name": "Second", "latitude": 3.3, "longitude": 4.4, "time": "00:15"},
        ]
        results = [
            {
                "Moon": position(15, "west", "low"),
                "Jupiter": position(60, "east", "high"),
                "Saturn": position(30, "south", "halfway up"),
            },
            {
                "Moon": position(-10, "west", "low"),
                "Jupiter": position(-20, "east", "low"),
                "Saturn": position(-30, "south", "low"),
            },
        ]
        hidden_stars = {
            name: position(-10, "north", "low")
            for name in star_facts()
        }
        with patch("main.get_positions", side_effect=results) as get_positions:
            with patch("main.get_star_positions", return_value=hidden_stars) as get_stars:
                with patch("main.is_dark_at", return_value=True):
                    with patch("main.find_iss_passes", return_value=[]):
                        evening = datetime(2026, 10, 15, 18, 0, tzinfo=TZ)
                        records, facts, _ = main._natsu_stops(
                            stops, evening, evening, "ephemeris", "timescale"
                        )
        self.assertEqual(
            get_positions.call_args_list,
            [
                call(1.1, 2.2, evening.replace(hour=19, minute=30), "ephemeris", "timescale"),
                call(3.3, 4.4, evening.replace(day=16, hour=0, minute=15), "ephemeris", "timescale"),
            ],
        )
        self.assertEqual(get_positions.call_count, 2)
        self.assertEqual(records[0]["target"]["object"], "Jupiter")
        self.assertEqual(records[1]["status"], "nothing above the horizon at this stop")
        self.assertEqual(records[1]["when"].date().isoformat(), "2026-10-16")
        self.assertNotIn("best_window", facts)
        self.assertEqual(
            [args.args[2] for args in get_stars.call_args_list],
            [
                evening.replace(hour=19, minute=30),
                evening.replace(day=16, hour=0, minute=15),
            ],
        )

    def test_natsu_daylight_stop_skips_positions_and_sets_exact_status(self):
        stops = [
            {"name": "Daylight", "latitude": 5.0, "longitude": 6.0, "time": "19:30"}
        ]
        evening = datetime(2026, 10, 15, 18, 0, tzinfo=TZ)
        with patch("main.is_dark_at", return_value=False):
            with patch("main.get_positions") as positions:
                with patch("main.get_star_positions") as get_stars:
                    records, facts, _ = main._natsu_stops(
                        stops, evening, evening, "ephemeris", "timescale"
                    )
        positions.assert_not_called()
        get_stars.assert_not_called()
        self.assertEqual(records[0]["status"], "sky not dark yet at this stop")
        self.assertIsNone(records[0]["target"])
        self.assertNotIn("best_window", facts)

    def test_route_span_uses_first_and_last_stop_dates(self):
        first = datetime(2026, 10, 15, 23, 30, tzinfo=TZ)
        last = datetime(2026, 10, 16, 0, 15, tzinfo=TZ)
        records = [{"when": first}, {"when": last}]
        self.assertEqual(
            main._route_span(records, first),
            "Route (Asia/Kolkata): Oct 15, 2026, 11:30 PM to Oct 16, 2026, 12:15 AM",
        )

    def test_natsu_route_facts_do_not_include_global_window(self):
        stops = [
            {"name": "Route stop", "latitude": 5.0, "longitude": 6.0, "time": "19:30"}
        ]
        evening = datetime(2026, 10, 15, 18, 0, tzinfo=TZ)
        with patch("main.is_dark_at", return_value=True):
            with patch("main.get_positions", return_value={
                "Moon": position(15, "west", "low"),
                "Jupiter": position(40, "east", "high"),
                "Saturn": position(-5, "south", "low"),
            }):
                with patch("main.get_star_positions", return_value=star_facts()):
                    records, facts, _ = main._natsu_stops(
                        stops, evening, evening, "ephemeris", "timescale"
                    )
        self.assertEqual(facts["route_stops"][0]["target"]["object"], "Jupiter")
        self.assertNotIn("best_window", facts)
        self.assertNotIn("positions", facts)
        self.assertEqual(records[0]["date"], "Oct 15, 2026")

    def test_natsu_star_can_be_highest_and_each_stop_uses_own_inputs(self):
        stops = [
            {"name": "First", "latitude": 10.0, "longitude": 20.0, "time": "19:30"},
            {"name": "Second", "latitude": -10.0, "longitude": 30.0, "time": "20:15"},
        ]
        evening = datetime(2026, 10, 15, 18, 0, tzinfo=TZ)
        below_planets = {
            "Moon": position(-1),
            "Jupiter": position(-2),
            "Saturn": position(-3),
        }
        first_stars = star_facts()
        for name in first_stars:
            first_stars[name] = position(-10, "north", "low")
        first_stars["Sirius"] = position(55, "south-east", "halfway up")
        second_stars = dict(first_stars)
        second_stars["Vega"] = position(70, "north-east", "high")
        second_stars["Sirius"] = position(20, "south", "low")
        with patch("main.is_dark_at", return_value=True):
            with patch("main.get_positions", return_value=below_planets):
                with patch(
                    "main.get_star_positions",
                    side_effect=[first_stars, second_stars],
                ) as get_stars:
                    records, _, _ = main._natsu_stops(
                        stops, evening, evening, "ephemeris", "timescale"
                    )
        self.assertEqual(records[0]["target"]["object"], "Sirius")
        self.assertEqual(records[0]["target"]["direction"], "south-east")
        self.assertEqual(records[1]["target"]["object"], "Vega")
        self.assertEqual(
            [(args[0], args[1], args[2].strftime("%H:%M")) for args, _ in get_stars.call_args_list],
            [(10.0, 20.0, "19:30"), (-10.0, 30.0, "20:15")],
        )

    def test_natsu_uses_each_changed_location_component_and_time(self):
        evening = datetime(2026, 10, 15, 18, 0, tzinfo=TZ)
        variants = [
            ("latitude", -10.0, -10.0, 20.0, "19:30"),
            ("longitude", 40.0, 10.0, 40.0, "19:30"),
            ("time", "21:00", 10.0, 20.0, "21:00"),
        ]
        for field, changed, expected_lat, expected_lon, expected_time in variants:
            with self.subTest(field=field):
                stop = {
                    "name": "One",
                    "latitude": 10.0,
                    "longitude": 20.0,
                    "time": "19:30",
                }
                stop[field] = changed
                with patch("main.is_dark_at", return_value=True):
                    with patch("main.get_positions", return_value={}):
                        with patch(
                            "main.get_star_positions", return_value=star_facts()
                        ) as get_stars:
                            with patch("main.find_iss_passes", return_value=[]):
                                main._natsu_stops(
                                    [stop], evening, evening, "ephemeris", "timescale"
                                )
                args = get_stars.call_args.args
                self.assertEqual(args[0], expected_lat)
                self.assertEqual(args[1], expected_lon)
                self.assertEqual(args[2].strftime("%H:%M"), expected_time)

    def test_demo_loads_example_stops_even_if_personal_file_exists(self):
        root = Path(self.temp.name)
        (root / "stops.local.json").write_text(
            '[{"name":"Private","latitude":1,"longitude":2,"time":"20:00"}]',
            encoding="utf-8",
        )
        (root / "stops.example.json").write_text(
            '[{"name":"Fictional","latitude":0,"longitude":0,"time":"20:00"}]',
            encoding="utf-8",
        )
        with patch.object(main, "PROJECT_DIR", root):
            self.assertEqual(main._load_stops(True)[0]["name"], "Fictional")
            self.assertEqual(main._load_stops(False)[0]["name"], "Private")


class StarPositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.ephemeris, cls.timescale = load_sky_data()
        except FileNotFoundError as error:
            raise unittest.SkipTest(str(error)) from error

    def test_fixed_time_polaris_and_southern_cross_by_latitude(self):
        when = datetime(2026, 10, 15, 2, 0, tzinfo=TZ)
        north = stars.get_star_positions(50.0, 0.0, when, self.ephemeris, self.timescale)
        ten_north = stars.get_star_positions(10.0, 0.0, when, self.ephemeris, self.timescale)
        equator = stars.get_star_positions(0.0, 0.0, when, self.ephemeris, self.timescale)
        south = stars.get_star_positions(-35.0, 0.0, when, self.ephemeris, self.timescale)

        self.assertGreater(north["Polaris"]["altitude_degrees"], 15)
        self.assertEqual(north["Polaris"]["direction"], "north")
        self.assertTrue(ten_north["Polaris"]["above_horizon"])
        self.assertLessEqual(ten_north["Polaris"]["altitude_degrees"], 15)
        self.assertEqual(
            main._polaris_item(ten_north)["text"],
            "Polaris is low from here: you need a clear north horizon.",
        )
        self.assertTrue(equator["Polaris"]["above_horizon"])
        self.assertLessEqual(equator["Polaris"]["altitude_degrees"], 15)
        self.assertEqual(
            main._polaris_item(equator)["text"],
            "Polaris is low from here: you need a clear north horizon.",
        )
        self.assertFalse(south["Polaris"]["above_horizon"])
        self.assertEqual(
            main._polaris_item(south)["text"],
            "Polaris is not visible from this latitude",
        )
        north_guides = applicable_guides(north)
        south_guides = applicable_guides(south)
        self.assertIn("Big Dipper", [guide["name"] for guide in north_guides])
        self.assertNotIn("Southern Cross", [guide["name"] for guide in north_guides])
        self.assertIn("Southern Cross", [guide["name"] for guide in south_guides])
        self.assertNotIn("Big Dipper", [guide["name"] for guide in south_guides])
        self.assertNotIn(
            "Southern Cross",
            [guide["name"] for guide in applicable_guides(ten_north)],
        )
        self.assertNotIn(
            "Southern Cross",
            [guide["name"] for guide in applicable_guides(equator)],
        )

    def test_big_dipper_guide_requires_every_anchor_above(self):
        anchors = ("Dubhe", "Merak", "Polaris")
        positions = {name: position(20) for name in anchors}
        self.assertIn("Big Dipper", [guide["name"] for guide in applicable_guides(positions)])
        positions["Merak"] = position(-1)
        self.assertNotIn("Big Dipper", [guide["name"] for guide in applicable_guides(positions)])

    def test_southern_cross_requires_only_its_three_cross_stars(self):
        positions = {
            name: position(20)
            for name in ("Acrux", "Mimosa", "Gacrux", "Hadar", "Alpha Centauri (Rigil Kentaurus)")
        }
        positions["Hadar"] = position(-5)
        positions["Alpha Centauri (Rigil Kentaurus)"] = position(-8)
        guides = [guide["name"] for guide in applicable_guides(positions)]
        self.assertIn("Southern Cross", guides)
        for anchor in ("Acrux", "Mimosa", "Gacrux"):
            changed_positions = dict(positions)
            changed_positions[anchor] = position(-1)
            self.assertNotIn(
                "Southern Cross",
                [guide["name"] for guide in applicable_guides(changed_positions)],
            )

    def test_every_catalog_star_has_apparent_magnitude_and_hipparcos_id(self):
        for name, record in stars.STAR_CATALOG.items():
            with self.subTest(name=name):
                self.assertIn("apparent_magnitude", record)
                self.assertIn("hip", record)

    def test_bright_star_list_is_limited_to_five_visible_catalog_stars(self):
        positions = {
            name: position(10, "north-east", "low")
            for name in stars.BRIGHT_STARS
        }
        positions["Sirius"] = position(-1, "south", "low")
        selected = stars.brightest_visible_stars(positions)
        self.assertEqual(len(selected), 5)
        self.assertNotIn("Sirius", [item["name"] for item in selected])
        magnitudes = [
            stars.BRIGHT_STARS[item["name"]]["apparent_magnitude"]
            for item in selected
        ]
        self.assertEqual(magnitudes, sorted(magnitudes))

    def test_equal_magnitudes_use_higher_altitude_as_tie_break(self):
        catalog = {
            name: dict(record)
            for name, record in stars.BRIGHT_STARS.items()
        }
        catalog["Sirius"]["apparent_magnitude"] = -1.0
        catalog["Vega"]["apparent_magnitude"] = -1.0
        positions = {
            name: position(-1, "north", "low")
            for name in catalog
        }
        positions["Sirius"] = position(20, "south", "halfway up")
        positions["Vega"] = position(70, "west", "high")
        with patch.dict(stars.BRIGHT_STARS, catalog, clear=True):
            selected = stars.brightest_visible_stars(positions, limit=2)
        self.assertEqual([item["name"] for item in selected], ["Vega", "Sirius"])

    def test_fixed_place_and_time_select_brightest_visible_not_first_catalog_rows(self):
        when = datetime(2026, 10, 15, 2, 0, tzinfo=TZ)
        positions = stars.get_star_positions(
            50.0, 0.0, when, self.ephemeris, self.timescale
        )
        first_five_catalog_names = list(stars.BRIGHT_STARS)[:5]
        selected = stars.brightest_visible_stars(positions)
        selected_names = [star["name"] for star in selected]
        self.assertNotEqual(selected_names, first_five_catalog_names)
        self.assertEqual(
            selected_names,
            ["Vega", "Capella", "Altair", "Aldebaran", "Fomalhaut"],
        )
        for previous, following in zip(selected, selected[1:]):
            previous_key = (
                previous["apparent_magnitude"],
                -previous["altitude_degrees"],
            )
            following_key = (
                following["apparent_magnitude"],
                -following["altitude_degrees"],
            )
            self.assertLessEqual(previous_key, following_key)

if __name__ == "__main__":
    unittest.main()
