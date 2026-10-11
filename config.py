"""Settings for Sky Quest. Fill in your observing location before a real run."""

import os


def _coordinate_from_environment(name: str) -> float | None:
    """Read a coordinate without storing a personal location in this file."""
    value = os.environ.get(name)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a decimal coordinate.") from error


# Set these locally with SKY_QUEST_LATITUDE and SKY_QUEST_LONGITUDE.
LATITUDE = _coordinate_from_environment("SKY_QUEST_LATITUDE")
LONGITUDE = _coordinate_from_environment("SKY_QUEST_LONGITUDE")

TIMEZONE = "Asia/Kolkata"
MODEL_NAME = "gemma3:1b"
PERSONA = "calm"  # Choose: calm, coach, precise, or quiet.

# Tune the astronomy-based score. Planet points reach their maximum at 90 degrees.
JUPITER_MAX_SCORE = 10.0
SATURN_MAX_SCORE = 10.0
MOON_MAX_PENALTY = 8.0
ISS_PASS_BONUS = 8.0

# Night scoring uses 15-minute slots and chooses the best consecutive 60 minutes.
SCORING_SLOT_MINUTES = 15
BEST_WINDOW_MINUTES = 60
SCORING_DURATION_HOURS = 3
