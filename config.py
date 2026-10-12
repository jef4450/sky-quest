"""Settings for Sky Quest. Fill in your observing location before a real run."""

import os
import math


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
PLACE_LABEL = os.environ.get("SKY_QUEST_PLACE_LABEL", "My observing place")
WINDOW_FACING = None
WINDOW_FIELD_OF_VIEW = 120.0
WINDOW_MIN_ALTITUDE = 10.0
MODEL_NAME = "gemma3:1b"
PERSONA = "calm"  # Choose: calm, coach, precise, or quiet.
DEPTH = "casual"  # Choose: casual, explorer, or deep.


def _validate_window_settings() -> None:
    if WINDOW_FACING is not None:
        compass_points = {
            "north", "north-east", "east", "south-east",
            "south", "south-west", "west", "north-west",
        }
        if isinstance(WINDOW_FACING, str):
            if WINDOW_FACING.lower() not in compass_points:
                raise ValueError(
                    "WINDOW_FACING must be a compass direction or degrees from 0 to 360."
                )
        elif (
            isinstance(WINDOW_FACING, bool)
            or not isinstance(WINDOW_FACING, (int, float))
            or not math.isfinite(WINDOW_FACING)
            or not 0 <= WINDOW_FACING <= 360
        ):
            raise ValueError(
                "WINDOW_FACING must be a compass direction or degrees from 0 to 360."
            )

    if (
        isinstance(WINDOW_FIELD_OF_VIEW, bool)
        or not isinstance(WINDOW_FIELD_OF_VIEW, (int, float))
        or not math.isfinite(WINDOW_FIELD_OF_VIEW)
        or not 0 < WINDOW_FIELD_OF_VIEW <= 360
    ):
        raise ValueError("WINDOW_FIELD_OF_VIEW must be greater than 0 and at most 360.")

    if (
        isinstance(WINDOW_MIN_ALTITUDE, bool)
        or not isinstance(WINDOW_MIN_ALTITUDE, (int, float))
        or not math.isfinite(WINDOW_MIN_ALTITUDE)
        or not 0 <= WINDOW_MIN_ALTITUDE <= 90
    ):
        raise ValueError("WINDOW_MIN_ALTITUDE must be from 0 to 90 degrees.")


_validate_window_settings()

# Tune the astronomy-based score. Planet points reach their maximum at 90 degrees.
JUPITER_MAX_SCORE = 10.0
SATURN_MAX_SCORE = 10.0
MOON_MAX_PENALTY = 8.0
ISS_PASS_BONUS = 8.0

# Night scoring uses 15-minute slots and chooses the best consecutive 60 minutes.
SCORING_SLOT_MINUTES = 15
BEST_WINDOW_MINUTES = 60
SCORING_DURATION_HOURS = 3
