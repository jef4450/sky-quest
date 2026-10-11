"""Score consecutive observing slots using sky facts calculated by sky.py."""

from datetime import datetime, timedelta

import config
from sky import get_positions, localize


def _format_time(when: datetime) -> str:
    return when.strftime("%I:%M %p").lstrip("0")


def _parse_pass_start(label: str, reference: datetime) -> datetime:
    """Parse the local time label returned by sky.find_iss_passes."""
    parsed = datetime.strptime(label, "%b %d, %I:%M %p")
    candidate = parsed.replace(year=reference.year, tzinfo=reference.tzinfo)
    if candidate < reference - timedelta(days=1):
        candidate = candidate.replace(year=reference.year + 1)
    return candidate


def _overlapping_passes(iss_passes: list, start: datetime, end: datetime) -> list:
    """Return the supplied visible ISS passes that overlap a slot."""
    matches = []
    for iss_pass in iss_passes:
        pass_start = _parse_pass_start(iss_pass["start"], start)
        pass_end = pass_start + timedelta(minutes=iss_pass["duration_minutes"])
        if pass_start < end and pass_end > start:
            matches.append((pass_start, pass_end))
    return matches


def _slot_score(
    positions: dict,
    moon_illumination: float,
    iss_passes: list,
    start: datetime,
    end: datetime,
) -> dict:
    """Score one slot using only calculated positions and visible-pass facts."""
    components = {}
    for planet, max_score in (
        ("Jupiter", config.JUPITER_MAX_SCORE),
        ("Saturn", config.SATURN_MAX_SCORE),
    ):
        position = positions[planet]
        altitude = (
            max(0.0, min(90.0, position["altitude_degrees"]))
            if position["above_horizon"]
            else 0.0
        )
        components[planet.lower()] = round(max_score * altitude / 90.0, 2)

    moon = positions["Moon"]
    if moon["above_horizon"]:
        altitude_factor = max(0.0, min(90.0, moon["altitude_degrees"])) / 90.0
        illumination = max(0.0, min(1.0, moon_illumination))
        components["moon_penalty"] = round(
            config.MOON_MAX_PENALTY * illumination * altitude_factor, 2
        )
    else:
        components["moon_penalty"] = 0.0

    passes = _overlapping_passes(iss_passes, start, end)
    components["iss_bonus"] = round(config.ISS_PASS_BONUS * len(passes), 2)
    total = round(
        components["jupiter"]
        + components["saturn"]
        - components["moon_penalty"]
        + components["iss_bonus"],
        2,
    )
    return {
        "start": start,
        "end": end,
        "score": total,
        "components": components,
        "positions": positions,
        "iss_passes": passes,
    }


def _window_reasons(window_slots: list[dict]) -> list[str]:
    """Summarize the clearest planet, Moon, and ISS facts in the chosen window."""
    reasons = []
    for planet in ("Jupiter", "Saturn"):
        observations = [
            (slot["start"] + (slot["end"] - slot["start"]) / 2, slot["positions"][planet])
            for slot in window_slots
        ]
        best_time, best_position = max(
            observations, key=lambda item: item[1]["altitude_degrees"]
        )
        if best_position["above_horizon"]:
            if best_position["height"] == "high":
                description = "high"
            elif best_position["height"] == "halfway up":
                description = "halfway up"
            else:
                description = "above the horizon"
            reasons.append(f"{planet} is {description} around {_format_time(best_time)}")
        else:
            reasons.append(f"{planet} stays below the horizon in this window")

    moon_observations = [slot["positions"]["Moon"] for slot in window_slots]
    if all(not moon["above_horizon"] for moon in moon_observations):
        reasons.append("Moon stays below the horizon during this window")
    else:
        moon_penalty = max(slot["components"]["moon_penalty"] for slot in window_slots)
        if moon_penalty > 0:
            reasons.append(
                f"Moon is up; its peak score penalty is {moon_penalty:g} points"
            )
        else:
            reasons.append("Moon is above the horizon during this window")

    seen_passes = set()
    for slot in window_slots:
        for pass_start, _ in slot["iss_passes"]:
            if pass_start not in seen_passes:
                seen_passes.add(pass_start)
                reasons.append(f"ISS pass at {_format_time(pass_start)}")
    return reasons[:4]


def _empty_result(message: str, per_slot_scores: list[dict] | None = None) -> dict:
    """Return a consistent, safe result when no complete window can be scored."""
    return {
        "window_start": None,
        "window_end": None,
        "start": None,
        "end": None,
        "total_score": 0.0,
        "per_slot_scores": per_slot_scores or [],
        "reasons": [],
        "positions": {},
        "message": message,
    }


def score_night(
    lat: float,
    lon: float,
    dark_start: datetime,
    moon_illumination: float,
    iss_passes: list,
    ephemeris,
    timescale,
) -> dict:
    """Score 15-minute slots and return the highest-scoring consecutive window."""
    slot_minutes = config.SCORING_SLOT_MINUTES
    window_minutes = config.BEST_WINDOW_MINUTES
    duration_hours = config.SCORING_DURATION_HOURS
    if (
        slot_minutes <= 0
        or window_minutes <= 0
        or duration_hours <= 0
        or window_minutes % slot_minutes != 0
    ):
        return _empty_result(
            "Scoring needs positive durations and a window that is a multiple of the slot length."
        )

    start_of_night = localize(dark_start)
    slot_length = timedelta(minutes=slot_minutes)
    window_slot_count = window_minutes // slot_minutes
    end_of_search = start_of_night + timedelta(hours=duration_hours)
    slots = []
    slot_start = start_of_night

    while slot_start + slot_length <= end_of_search:
        slot_end = slot_start + slot_length
        midpoint = slot_start + slot_length / 2
        positions = get_positions(lat, lon, midpoint, ephemeris, timescale)
        slot = _slot_score(
            positions, moon_illumination, iss_passes or [], slot_start, slot_end
        )
        slot["midpoint"] = midpoint
        slots.append(slot)
        slot_start = slot_end

    if len(slots) < window_slot_count:
        return _empty_result(
            "There are no usable dark slots long enough for the configured best window.",
            [
                {
                    "start": slot["start"],
                    "end": slot["end"],
                    "score": slot["score"],
                    "components": slot["components"],
                }
                for slot in slots
            ],
        )

    best_slots = None
    best_total = float("-inf")
    for first_index in range(len(slots) - window_slot_count + 1):
        candidate = slots[first_index:first_index + window_slot_count]
        candidate_total = round(sum(slot["score"] for slot in candidate), 2)
        if candidate_total > best_total:
            best_slots = candidate
            best_total = candidate_total

    if best_slots is None:
        return _empty_result("No complete observing window could be scored.")

    start = best_slots[0]["start"]
    end = best_slots[-1]["end"]
    return {
        "window_start": start,
        "window_end": end,
        "start": start,
        "end": end,
        "total_score": best_total,
        "per_slot_scores": [
            {
                "start": slot["start"],
                "end": slot["end"],
                "score": slot["score"],
                "components": slot["components"],
            }
            for slot in slots
        ],
        "reasons": _window_reasons(best_slots),
        "positions": best_slots[len(best_slots) // 2]["positions"],
        "message": "",
    }
