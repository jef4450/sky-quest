"""Focused tests for narration grounding, retries, fallbacks, and Ollama errors."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import ollama

import grounding_check
import narrate


FACTS = {
    "best_window": {"start": "9:00 PM", "end": "10:00 PM"},
    "positions": {
        "Moon": {
            "direction": "south-west",
            "height": "low",
            "above_horizon": False,
        },
        "Jupiter": {
            "direction": "east",
            "height": "high",
            "above_horizon": True,
        },
    },
    "moon_phase": "waxing crescent",
    "moonrise": "10:01 AM",
    "iss_passes": [],
}


class GroundingTests(unittest.TestCase):
    def test_unlisted_object_returns_consistent_failure_tuple(self):
        result = grounding_check.check_grounding("Mars is overhead.", FACTS)
        self.assertEqual(result, (False, "Unlisted celestial object(s): mars"))

    def test_wrong_object_direction_and_height_fail(self):
        passed, reason = grounding_check.check_grounding(
            "The Moon is high in the east.", FACTS
        )
        self.assertFalse(passed)
        self.assertIn("Moon", reason)

    def test_unprovided_weather_fails(self):
        passed, reason = grounding_check.check_grounding(
            "Clouds are gathering tonight.", FACTS
        )
        self.assertFalse(passed)
        self.assertIn("cloud", reason.lower())

    def test_invented_star_fails_when_only_vega_is_supplied(self):
        facts = {
            "stars": {
                "Vega": {
                    "direction": "east",
                    "height": "high",
                    "above_horizon": True,
                }
            }
        }
        passed, reason = grounding_check.check_grounding(
            "Sirius is high in the south.", facts
        )
        self.assertFalse(passed)
        self.assertEqual(reason, "Unlisted celestial object(s): sirius")

    def test_supplied_constellation_guide_name_is_allowed(self):
        facts = {
            "stars": {
                "Vega": {
                    "direction": "east",
                    "height": "high",
                    "above_horizon": True,
                }
            },
            "constellation_guides": [
                {"name": "Summer Triangle", "text": "Vega, Deneb, and Altair mark the Summer Triangle."}
            ],
        }
        passed, reason = grounding_check.check_grounding(
            "The Summer Triangle is ready to find.", facts
        )
        self.assertTrue(passed, reason)

    def test_invented_star_retries_once_then_falls_back_without_it(self):
        facts = {
            "stars": {
                "Vega": {
                    "direction": "east",
                    "height": "high",
                    "above_horizon": True,
                }
            }
        }
        with patch(
            "narrate._ask_ollama",
            side_effect=["Sirius is bright.", "Sirius is still bright."],
        ) as model:
            text, metadata = narrate.narrate_with_metadata(
                facts,
                "calm",
                sentence_count=1,
                validate_sentence_count=True,
            )
        self.assertEqual(model.call_count, 2)
        self.assertEqual(metadata["attempts_used"], 2)
        self.assertTrue(metadata["fell_back"])
        self.assertNotIn("Sirius", text)


class NarrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.temp_dir.name) / "gemma_slips.log"
        self.log_patch = patch.object(grounding_check, "SLIP_LOG", self.log_path)
        self.log_patch.start()
        self.addCleanup(self.log_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def test_bad_first_and_retry_call_model_exactly_twice_then_fallback(self):
        with patch("narrate._ask_ollama", side_effect=[
            "Mars is overhead.",
            "Mars is still overhead.",
        ]) as model:
            text, metadata = narrate.narrate_with_metadata(FACTS, "quiet")

        model.assert_has_calls([
            unittest.mock.call(FACTS, "quiet", ""),
            unittest.mock.call(FACTS, "quiet", "Unlisted celestial object(s): mars"),
        ])
        self.assertEqual(model.call_count, 2)
        self.assertTrue(metadata["fell_back"])
        self.assertFalse(metadata["passed"])
        self.assertEqual(metadata["attempts_used"], 2)
        self.assertEqual(len(metadata["failure_reasons"]), 2)
        self.assertIn("Jupiter: high, east, above the horizon.", text)
        self.assertNotIn("Mars", text)

        records = [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record["persona"] == "quiet" for record in records))
        self.assertTrue(all(record["failure_type"] == "grounding_failure" for record in records))
        self.assertTrue(all(record["timestamp"] for record in records))

    def test_public_narrate_keeps_string_return_for_existing_callers(self):
        with patch("narrate._ask_ollama", return_value="The Moon is low in the south-west."):
            result = narrate.narrate(FACTS, "calm")
        self.assertIsInstance(result, str)

    def test_configured_personas_are_included_in_model_prompt(self):
        expected_styles = {
            "calm": "calm and reassuring",
            "coach": "encouraging, like a friendly outdoor coach",
            "precise": "clear and precise",
            "quiet": "quiet, gentle, and minimal",
        }
        client = SimpleNamespace(
            generate=lambda **kwargs: (
                self.assertIn(expected_styles[persona], kwargs["prompt"])
                or SimpleNamespace(response="A grounded response.")
            ),
            close=lambda: None,
        )
        with patch("ollama.Client", return_value=client):
            for persona in expected_styles:
                self.assertEqual(narrate._ask_ollama(FACTS, persona), "A grounded response.")

    def test_connection_error_has_specific_message_and_log(self):
        with patch("narrate._ask_ollama", side_effect=httpx.ConnectError("connection refused")):
            with patch("builtins.print") as printed:
                text, metadata = narrate.narrate_with_metadata(FACTS)

        self.assertTrue(metadata["fell_back"])
        self.assertEqual(metadata["attempts_used"], 1)
        self.assertIn("Start the Ollama app or service", printed.call_args.args[0])
        record = json.loads(self.log_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(record["failure_type"], "ollama_not_running")
        self.assertNotIn("8.1833", json.dumps(record))
        self.assertIn("Jupiter", text)

    def test_missing_model_has_pull_command_and_log(self):
        error = ollama.ResponseError("model 'gemma3:1b' not found", status_code=404)
        with patch("narrate._ask_ollama", side_effect=error):
            with patch("builtins.print") as printed:
                _, metadata = narrate.narrate_with_metadata(FACTS)

        self.assertTrue(metadata["fell_back"])
        self.assertIn("ollama pull gemma3:1b", printed.call_args.args[0])
        record = json.loads(self.log_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(record["failure_type"], "model_unavailable")

    def test_ollama_client_uses_sixty_second_timeout(self):
        fake_client = SimpleNamespace(
            generate=lambda **kwargs: SimpleNamespace(response="A grounded response."),
            close=lambda: None,
        )
        with patch("ollama.Client", return_value=fake_client) as client_factory:
            text = narrate._ask_ollama(FACTS, "precise")
        client_factory.assert_called_once_with(timeout=60.0)
        self.assertEqual(text, "A grounded response.")

    def test_one_sentence_option_is_sent_to_local_model(self):
        fake_client = SimpleNamespace(
            generate=lambda **kwargs: (
                self.assertIn(
                    "Write exactly 1 short, friendly sentence",
                    kwargs["prompt"],
                )
                or SimpleNamespace(response="A grounded response.")
            ),
            close=lambda: None,
        )
        with patch("ollama.Client", return_value=fake_client):
            text = narrate._ask_ollama(FACTS, "coach", sentence_count=1)
        self.assertEqual(text, "A grounded response.")

    def test_deterministic_requests_use_fixed_seed_and_zero_temperature(self):
        generated = {}
        fake_client = SimpleNamespace(
            generate=lambda **kwargs: (
                generated.update(kwargs)
                or SimpleNamespace(response="Jupiter is high in the east.")
            ),
            close=lambda: None,
        )
        with patch("ollama.Client", return_value=fake_client):
            narrate._ask_ollama(
                FACTS,
                "calm",
                deterministic=True,
            )
        self.assertEqual(
            generated["options"],
            {"temperature": 0, "seed": 42},
        )

    def test_sentence_count_and_required_fact_retry_then_use_fact_only_fallback(self):
        facts = dict(FACTS)
        facts["narration_line"] = "Jupiter is high in the east."
        with patch(
            "narrate._ask_ollama",
            side_effect=[
                "Jupiter is high in the east. Go!",
                "Jupiter is high in the east. Keep going!",
            ],
        ) as model:
            text, metadata = narrate.narrate_with_metadata(
                facts,
                "coach",
                sentence_count=1,
                validate_sentence_count=True,
                required_fact="Jupiter",
            )

        self.assertEqual(model.call_count, 2)
        self.assertTrue(metadata["fell_back"])
        self.assertEqual(metadata["attempts_used"], 2)
        self.assertEqual(text, "Jupiter is high in the east.")
        self.assertEqual(text.count("."), 1)

    def test_coordinates_are_redacted_in_log(self):
        coordinate_pair = ".".join(("12", "345678")) + ", " + ".".join(("77", "123456"))
        grounding_check.append_slip(
            f"Location was {coordinate_pair}",
            "Unsupported claim.",
            persona="coach",
        )
        record = json.loads(self.log_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertNotIn(coordinate_pair, json.dumps(record))
        self.assertIn("[coordinates redacted]", record["text"])


if __name__ == "__main__":
    unittest.main()
