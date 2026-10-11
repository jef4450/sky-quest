"""Simple 15-minute observing-window scores based on calculated sky facts."""

from datetime import datetime, timedelta

from sky import get_positions, localize


def _slot_score(positions: dict, moon_illumination: float, iss_passes: list, start, end):
    score = 0
    reasons = []
    for planet in ("Jupiter", "Saturn"):
        position = positions[planet]
        altitude = position["altitude_degrees"]
        if altitude >= 60:
            score += 5
            reasons.append(f"{planet} is high")
        elif altitude >= 30:
            score += 3
            reasons.append(f"{planet} is halfway up")
        elif altitude > 0:
            score += 1

    moon = positions["Moon"]
    if moon["above_horizon"] and moon_illumination >= 0.55:
        score -= 2
        reasons.append("the bright Moon is up")

    has_iss = any(
        _parse_pass_start(item["start"], start) < end
        and _parse_pass_start(item["start"], start)
        + timedelta(minutes=item["duration_minutes"]) > start
        for item in iss_passes
    )
    if has_iss:
        score += 4
        reasons.append("an ISS pass is expected")
    return score, reasons, has_iss


def _parse_pass_start(label: str, reference: datetime) -> datetime:
    """Interpret a pass label created by sky.find_iss_passes in the same local year."""
    parsed = datetime.strptime(label, "%b %d, %I:%M %p")
    return parsed.replace(year=reference.year, tzinfo=reference.tzinfo)


def score_night(
    lat: float,
    lon: float,
    dark_start: datetime,
    moon_illumination: float,
    iss_passes: list,
    ephemeris,
    timescale,
    *,
    slot_minutes: int = 15,
    duration_hours: int = 3,
) -> dict | None:
    """Score consecutive slots after astronomical darkness and return the best one."""
    start_of_night = localize(dark_start)
    slot_length = timedelta(minutes=slot_minutes)
    end_of_search = start_of_night + timedelta(hours=duration_hours)
    slots = []
    slot_start = start_of_night
    while slot_start < end_of_search:
        slot_end = min(slot_start + slot_length, end_of_search)
        midpoint = slot_start + (slot_end - slot_start) / 2
        positions = get_positions(lat, lon, midpoint, ephemeris, timescale)
        score, reasons, has_iss = _slot_score(
            positions, moon_illumination, iss_passes, slot_start, slot_end
        )
        slots.append({
            "start": slot_start,
            "end": slot_end,
            "score": score,
            "reasons": reasons,
            "positions": positions,
            "has_iss": has_iss,
        })
        slot_start = slot_end

    if not slots:
        return None

    best = max(slots, key=lambda slot: slot["score"])
    if not best["reasons"]:
        best["reasons"].append("the Moon, Jupiter, and Saturn positions are included in this window")
    return best
