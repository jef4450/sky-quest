"""Check narration against sky facts and append one-line grounding logs."""

from datetime import datetime
import json
import re
from decimal import Decimal
from pathlib import Path


SLIP_LOG = Path(__file__).resolve().parent / "gemma_slips.log"
CELESTIAL_TERMS = (
    "moon", "sun", "mercury", "venus", "earth", "mars", "jupiter", "saturn",
    "uranus", "neptune", "pluto", "ceres", "eris", "haumea", "makemake",
    "iss", "international space station", "star", "stars", "polaris",
    "north star", "sirius", "vega", "arcturus", "betelgeuse", "rigel",
    "altair", "deneb", "capella", "aldebaran", "antares", "spica",
    "regulus", "procyon", "pollux", "fomalhaut", "canopus", "achernar",
    "alpha centauri", "rigil kentaurus", "acrux", "hadar", "mimosa", "gacrux",
    "dubhe", "merak",
    "schedar", "caph", "big dipper", "cassiopeia", "summer triangle",
    "southern cross", "south celestial pole", "orion",
    "albireo", "mizar", "epsilon lyrae", "pleiades", "beehive cluster",
    "double cluster", "hercules cluster", "sagittarius cluster",
    "orion nebula", "ring nebula", "lagoon nebula", "andromeda galaxy",
    "bode's galaxy", "whirlpool galaxy", "m 45", "m 44", "ngc 869",
    "ngc 884", "m 13", "ngc 6121", "m 22", "m 42", "m 57", "m 8",
    "m 31", "m 81", "m 51",
    "pleiades", "milky way", "andromeda", "galaxy", "galaxies", "nebula",
    "nebulae", "meteor", "meteors", "comet", "comets", "constellation",
    "constellations", "asteroid", "asteroids", "planet", "planets",
    "eclipse", "eclipses", "aurora", "auroras",
)
DIRECTION_PATTERN = re.compile(
    r"\b(?:north[\s-]?east|south[\s-]?east|south[\s-]?west|north[\s-]?west|"
    r"north|south|east|west)\b",
    re.IGNORECASE,
)
TIME_PATTERN = re.compile(
    r"\b(?:(?:[01]?\d|2[0-3]):[0-5]\d(?:\s?[ap]\.?m\.?)?|"
    r"(?:[1-9]|1[0-2])\s?[ap]\.?m\.?)\b",
    re.IGNORECASE,
)
NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")
NUMBER_WORD_PATTERN = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
    r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
    r"eighty|ninety|hundred|thousand|dozen|half|quarter|twice|"
    r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b",
    re.IGNORECASE,
)
UNSUPPORTED_CLAIM_PATTERN = re.compile(
    r"\b(?:weather|clouds?|cloudy|overcast|rain(?:y|ing)?|snow(?:y|ing)?|"
    r"wind(?:y|s|ing)?|fog(?:gy)?|mist(?:y)?|storm(?:y|s)?|"
    r"temperature|humid(?:ity)?|clear skies?|meteor showers?|"
    r"cloudless|eclipses?|conjunctions?|alignments?|auroras?|satellites?|"
    r"events?|festivals?|concerts?|parades?|celebrations?|parties?|"
    r"bright|brightness|brighter|dim|dimmer|glowing|glow|shine|shining|"
    r"descent|descending|descends|turning|moving|traveling|travelling|"
    r"climbing|half-circle)\b",
    re.IGNORECASE,
)
EVENT_PATTERN = re.compile(
    r"\b(?P<object>moon|sun)\b[^.!?]{0,60}?"
    r"\b(?P<verb>rise|rises|rose|rising|set|sets|setting)\b",
    re.IGNORECASE,
)
PHASE_PATTERN = re.compile(
    r"\b(?:new moon|waxing crescent|first quarter|waxing gibbous|full moon|"
    r"waning gibbous|last quarter|waning crescent)\b",
    re.IGNORECASE,
)
PHASE_CHANGE_PATTERN = re.compile(
    r"\b(?:will|soon|later|continue to|going to)\b[^.!?]{0,40}"
    r"\b(?:wax|wane|become|grow|turn into)\w*\b",
    re.IGNORECASE,
)
COORDINATES_PATTERN = re.compile(
    r"(?<!\w)[+-]?\d{1,3}\.\d{3,}\s*[,/]\s*[+-]?\d{1,3}\.\d{3,}(?!\w)"
)


def _fact_text(facts: dict) -> str:
    return json.dumps(facts, ensure_ascii=False, sort_keys=True)


def _canonical_direction(direction: str) -> str:
    return direction.lower().replace("-", "").replace(" ", "")


def _position_facts(facts: dict) -> dict[str, list[dict]]:
    """Collect position facts from each card mode's supplied sky data."""
    found: dict[str, list[dict]] = {}

    def remember_positions(source: dict) -> None:
        for key in ("positions", "stars", "telescope_targets"):
            for name, position in source.get(key, {}).items():
                if isinstance(position, dict):
                    fact_name = str(position.get("name", name))
                    found.setdefault(fact_name, []).append(position)
                    found.setdefault(str(name), []).append(position)
                    if fact_name.lower().startswith("alpha centauri"):
                        found.setdefault("Alpha Centauri", []).append(position)
                        found.setdefault("Rigil Kentaurus", []).append(position)

    remember_positions(facts)
    for row in facts.get("timeline", []):
        if isinstance(row, dict):
            remember_positions(row)
    for stop in facts.get("route_stops", []):
        if not isinstance(stop, dict):
            continue
        target = stop.get("target")
        if isinstance(target, dict) and target.get("object"):
            name = str(target["object"])
            found.setdefault(name, []).append(target)
            if name.lower().startswith("alpha centauri"):
                found.setdefault("Alpha Centauri", []).append(target)
                found.setdefault("Rigil Kentaurus", []).append(target)
    return found


def _clock_minutes(label: str | None) -> int | None:
    if not label:
        return None
    match = TIME_PATTERN.search(label)
    if not match:
        return None
    normalized = match.group().replace(".", "").upper()
    parsed = re.search(
        r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s?(?P<ampm>[AP]M)",
        normalized,
    )
    if not parsed:
        return None
    hour = int(parsed.group("hour")) % 12
    if parsed.group("ampm") == "PM":
        hour += 12
    return hour * 60 + int(parsed.group("minute"))


def _check_object_attributes(text: str, facts: dict) -> str:
    """Check position descriptions in the phrase following each named object."""
    positions = _position_facts(facts)
    names = sorted(positions, key=len, reverse=True)
    if not names:
        return ""

    object_pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(name) for name in names) + r")\b",
        re.IGNORECASE,
    )
    heights = {
        "low": re.compile(r"\blow\b|\bnear the horizon\b", re.IGNORECASE),
        "halfway up": re.compile(r"\bhalf(?:way|-way) up\b|\bmidway up\b", re.IGNORECASE),
        "high": re.compile(r"\bhigh\b|\boverhead\b", re.IGNORECASE),
    }

    for sentence in re.split(r"(?<=[.!?])\s+", text):
        mentions = list(object_pattern.finditer(sentence))
        for index, mention in enumerate(mentions):
            name = next(key for key in names if key.lower() == mention.group().lower())
            object_positions = positions[name]
            clause_end = mentions[index + 1].start() if index + 1 < len(mentions) else len(sentence)
            clause = sentence[mention.end():clause_end]

            directions = DIRECTION_PATTERN.findall(clause)
            if any(
                not any(
                    _canonical_direction(direction)
                    == _canonical_direction(position.get("direction", ""))
                    for position in object_positions
                )
                for direction in directions
            ):
                return f"{name} is paired with a direction that conflicts with its supplied position."

            for height, pattern in heights.items():
                if pattern.search(clause) and not any(
                    position.get("height") == height
                    for position in object_positions
                ):
                    supplied = ", ".join(sorted({
                        str(position.get("height"))
                        for position in object_positions
                    }))
                    return f"{name} is described as {height}, but the supplied height is {supplied}."

            says_above = bool(re.search(
                r"\b(?:above the horizon|visible|in the sky|up in the sky)\b",
                clause,
                re.IGNORECASE,
            ))
            says_below = bool(re.search(r"\bbelow the horizon\b", clause, re.IGNORECASE))
            if says_above and not any(
                position.get("above_horizon", False)
                for position in object_positions
            ):
                return f"{name} is described as visible, but supplied facts place it below the horizon."
            if says_below and not any(
                not position.get("above_horizon", False)
                for position in object_positions
            ):
                return f"{name} is described as below the horizon, but supplied facts place it above."
    return ""


def _check_events(text: str, facts: dict) -> str:
    """Reject unsupplied Sun/Moon events or times that conflict with the facts."""
    best_window = facts.get("best_window") or {}
    window_start = _clock_minutes(best_window.get("start"))
    window_end = _clock_minutes(best_window.get("end"))

    for sentence in re.split(r"(?<=[.!?])\s+", text):
        for claim in EVENT_PATTERN.finditer(sentence):
            body = claim.group("object").lower()
            verb = claim.group("verb").lower()
            rising = verb.startswith("ris") or verb == "rose"
            event_key = (
                "moonrise" if body == "moon" and rising
                else "moonset" if body == "moon"
                else None
            )
            if body == "sun" and not rising:
                event_key = "sunset"
            if event_key is None or not facts.get(event_key):
                return f"The {body} event is not present in the supplied facts."

            expected_time = _clock_minutes(facts[event_key])
            sentence_times = [_clock_minutes(item) for item in TIME_PATTERN.findall(sentence)]
            sentence_times = [value for value in sentence_times if value is not None]
            if sentence_times and expected_time not in sentence_times:
                return f"The {body} event is paired with a time that conflicts with {event_key}."

            context = sentence[claim.start("object"):claim.start("verb")].lower()
            claims_future = bool(re.search(r"\b(?:will|soon|upcoming|about to)\b", context))
            event_is_after_window = (
                window_end is not None
                and (
                    expected_time > window_end
                    or (expected_time < 5 * 60 and window_end >= 18 * 60)
                )
            )
            if claims_future and window_end is not None and not event_is_after_window:
                return f"The {body} event is described as upcoming after its supplied time."
            if verb in ("rising", "setting") and window_start is not None and window_end is not None:
                if not window_start <= expected_time <= window_end:
                    return f"The {body} is described as moving outside its supplied event time."

    phase = facts.get("moon_phase", "")
    for mentioned_phase in PHASE_PATTERN.findall(text):
        if mentioned_phase.lower() not in phase.lower():
            return f"Moon phase '{mentioned_phase}' conflicts with the supplied phase '{phase}'."
    if PHASE_CHANGE_PATTERN.search(text):
        return "A future Moon phase change is not included in the supplied facts."
    return ""


def check_grounding(text: str, facts: dict) -> tuple[bool, str]:
    """Return a consistent pass/failure tuple after checking claims against facts."""
    if not isinstance(text, str) or not text.strip():
        return False, "Narration is empty."
    if not isinstance(facts, dict):
        return False, "Supplied facts must be a dictionary."

    source = _fact_text(facts).lower()
    position_facts = _position_facts(facts)
    allowed_objects = {name.lower() for name in position_facts}
    if "alpha centauri" in allowed_objects or any(
        name.startswith("alpha centauri") for name in allowed_objects
    ):
        allowed_objects.add("rigil kentaurus")
        allowed_objects.add("alpha centauri")
    has_star_facts = bool(facts.get("stars")) or any(
        bool(row.get("stars"))
        for row in facts.get("timeline", [])
        if isinstance(row, dict)
    ) or any(
        str(stop.get("target", {}).get("object", "")).lower()
        not in {"", "moon", "jupiter", "saturn"}
        for stop in facts.get("route_stops", [])
        if isinstance(stop, dict) and isinstance(stop.get("target"), dict)
    )
    if has_star_facts:
        allowed_objects.update(("star", "stars"))
    if "polaris" in allowed_objects:
        allowed_objects.add("north star")
    if facts.get("iss_passes"):
        allowed_objects.update(("iss", "international space station"))
    if facts.get("sunset") or facts.get("dark_time"):
        allowed_objects.add("sun")
    guides = list(facts.get("constellation_guides", []))
    guides.extend(
        guide
        for row in facts.get("timeline", [])
        if isinstance(row, dict)
        for guide in row.get("constellation_guides", [])
    )
    allowed_objects.update(
        str(guide.get("name", "")).lower()
        for guide in guides
        if isinstance(guide, dict)
    )
    if guides:
        allowed_objects.update(("constellation", "constellations"))

    unknown_objects = sorted({
        term for term in CELESTIAL_TERMS
        if re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE)
        and term not in allowed_objects
    })
    if unknown_objects:
        return False, "Unlisted celestial object(s): " + ", ".join(unknown_objects)

    object_reason = _check_object_attributes(text, facts)
    if object_reason:
        return False, object_reason

    allowed_directions = {
        _canonical_direction(direction)
        for direction in DIRECTION_PATTERN.findall(source)
    }
    unknown_directions = sorted({
        direction for direction in DIRECTION_PATTERN.findall(text)
        if _canonical_direction(direction) not in allowed_directions
    })
    if unknown_directions:
        return False, "Direction(s) not present in supplied facts: " + ", ".join(unknown_directions)

    event_reason = _check_events(text, facts)
    if event_reason:
        return False, event_reason

    unknown_times = sorted({
        item.lower().replace(" ", "")
        for item in TIME_PATTERN.findall(text)
        if item.lower().replace(" ", "") not in {
            value.lower().replace(" ", "") for value in TIME_PATTERN.findall(source)
        }
    })
    if unknown_times:
        return False, "Time(s) not present in supplied facts: " + ", ".join(unknown_times)

    allowed_numbers = {
        Decimal(number)
        for number in NUMBER_PATTERN.findall(TIME_PATTERN.sub("", source))
    }
    unknown_numbers = sorted({
        number
        for number in NUMBER_PATTERN.findall(TIME_PATTERN.sub("", text))
        if Decimal(number) not in allowed_numbers
    })
    if unknown_numbers:
        return False, "Number(s) not present in supplied facts: " + ", ".join(unknown_numbers)

    allowed_number_words = {
        word.lower() for word in NUMBER_WORD_PATTERN.findall(source)
    }
    unknown_number_words = sorted({
        word.lower()
        for word in NUMBER_WORD_PATTERN.findall(text)
        if word.lower() not in allowed_number_words
    })
    if unknown_number_words:
        return False, "Number word(s) not present in supplied facts: " + ", ".join(unknown_number_words)

    unprovided_claims = sorted({
        claim.lower()
        for claim in UNSUPPORTED_CLAIM_PATTERN.findall(text)
        if claim.lower() not in source
    })
    if unprovided_claims:
        return False, "Unprovided weather, event, or visual claim(s): " + ", ".join(unprovided_claims)
    return True, ""


def _redact_coordinates(text: str) -> str:
    """Avoid persisting precise coordinate pairs in the narration log."""
    return COORDINATES_PATTERN.sub("[coordinates redacted]", text)


def append_slip(
    text: str,
    reason: str,
    *,
    persona: str = "unknown",
    failure_type: str = "grounding_failure",
) -> None:
    """Append one JSON record without storing precise coordinate pairs."""
    record = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "persona": persona,
        "failure_type": failure_type,
        "reason": _redact_coordinates(reason),
        "text": _redact_coordinates(text),
    }
    with SLIP_LOG.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
