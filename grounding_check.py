"""Check generated narration for celestial objects, directions, and numbers."""

import json
import re
from decimal import Decimal
from pathlib import Path


SLIP_LOG = Path(__file__).resolve().parent / "gemma_slips.log"
CELESTIAL_TERMS = (
    "moon", "sun", "mercury", "venus", "earth", "mars", "jupiter", "saturn",
    "uranus", "neptune", "pluto", "iss", "international space station",
    "star", "stars", "polaris", "north star", "sirius", "orion", "pleiades",
    "milky way", "meteor", "meteors", "comet", "comets", "constellation",
    "constellations", "galaxy", "galaxies",
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
    r"eighty|ninety|first|second|third|fourth|fifth|sixth|seventh|"
    r"eighth|ninth|tenth)\b",
    re.IGNORECASE,
)
UNSUPPORTED_CLAIM_PATTERN = re.compile(
    r"\b(?:bright|brightness|brighter|dim|dimmer|glowing|glow|shine|"
    r"shining|descent|descending|descends|turning|moving|traveling|"
    r"travelling|climbing|half-circle)\b",
    re.IGNORECASE,
)
EVENT_CLAIM_PATTERN = re.compile(
    r"\b(?P<object>moon|sun)\b[^.!?]{0,60}?"
    r"\b(?P<verb>rise|rises|rose|rising|set|sets|setting)\b",
    re.IGNORECASE,
)
PHASE_CHANGE_PATTERN = re.compile(
    r"\b(?:will|soon|later|continue to|going to)\b[^.!?]{0,40}"
    r"\b(?:wax|wane|become|grow|turn into)\w*\b",
    re.IGNORECASE,
)


def _fact_text(facts: dict) -> str:
    return json.dumps(facts, ensure_ascii=False, sort_keys=True)


def _canonical_direction(direction: str) -> str:
    return direction.lower().replace("-", "").replace(" ", "")


def _clock_minutes(label: str | None) -> int | None:
    if not label:
        return None
    match = TIME_PATTERN.search(label)
    if not match:
        return None
    parsed = re.search(
        r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s?(?P<ampm>[ap]m)",
        match.group().replace(".", ""),
        re.IGNORECASE,
    )
    if not parsed:
        return None
    hour = int(parsed.group("hour")) % 12
    if parsed.group("ampm").lower() == "pm":
        hour += 12
    return hour * 60 + int(parsed.group("minute"))


def _check_object_attributes(text: str, facts: dict) -> str:
    """Check directions and height/horizon claims in the clause for each object."""
    positions = facts.get("positions", {})
    names = sorted(positions, key=len, reverse=True)
    if not names:
        return ""

    object_pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(name) for name in names) + r")\b",
        re.IGNORECASE,
    )
    sentence_pattern = re.compile(r"[^.!?]+")
    height_terms = {
        "low": re.compile(r"\blow\b", re.IGNORECASE),
        "halfway up": re.compile(r"\bhalf(?:way|-way) up\b|\bmidway up\b", re.IGNORECASE),
        "high": re.compile(r"\bhigh\b|\boverhead\b", re.IGNORECASE),
    }

    for sentence in sentence_pattern.findall(text):
        mentions = list(object_pattern.finditer(sentence))
        for index, mention in enumerate(mentions):
            name = next(
                key for key in names
                if key.lower() == mention.group().lower()
            )
            position = positions[name]
            clause_end = mentions[index + 1].start() if index + 1 < len(mentions) else len(sentence)
            clause = sentence[mention.end():clause_end]

            directions = DIRECTION_PATTERN.findall(clause)
            expected_direction = _canonical_direction(position["direction"])
            if any(
                _canonical_direction(direction) != expected_direction
                for direction in directions
            ):
                return f"{name} is paired with a direction that does not match its position."

            for height, pattern in height_terms.items():
                if pattern.search(clause) and position["height"] != height:
                    return f"{name} is described as {height}, but the facts say {position['height']}."

            says_above = bool(re.search(
                r"\b(?:above the horizon|visible|in the sky|up in the sky)\b",
                clause,
                re.IGNORECASE,
            ))
            says_below = bool(re.search(r"\bbelow the horizon\b", clause, re.IGNORECASE))
            if says_above and not position["above_horizon"]:
                return f"{name} is described as visible, but the facts place it below the horizon."
            if says_below and position["above_horizon"]:
                return f"{name} is described as below the horizon, but the facts place it above."
    return ""


def _check_event_claims(text: str, facts: dict) -> str:
    """Reject unlisted Moon/Sun events and event timing that conflicts with the best window."""
    best_window = facts.get("best_window") or {}
    window_start = _clock_minutes(best_window.get("start"))
    window_end = _clock_minutes(best_window.get("end"))

    for sentence in re.split(r"(?<=[.!?])\s+", text):
        for claim in EVENT_CLAIM_PATTERN.finditer(sentence):
            object_name = claim.group("object").lower()
            verb = claim.group("verb").lower()
            rising = verb.startswith("ris") or verb == "rose"
            event_key = (
                "moonrise" if object_name == "moon" and rising
                else "moonset" if object_name == "moon"
                else None
            )
            if object_name == "sun" and not rising:
                event_key = "sunset"
            if event_key is None or not facts.get(event_key):
                return f"The {object_name} event is not listed in the facts."

            expected_time = _clock_minutes(facts[event_key])
            sentence_times = [_clock_minutes(item) for item in TIME_PATTERN.findall(sentence)]
            sentence_times = [value for value in sentence_times if value is not None]
            if sentence_times and expected_time not in sentence_times:
                return f"The {object_name} event is paired with the wrong time."

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
                return f"The {object_name} event is described as upcoming after it has already passed."
            if verb in ("rising", "setting") and window_start is not None and window_end is not None:
                if not window_start <= expected_time <= window_end:
                    return f"The {object_name} is described as moving during a different time."

    if PHASE_CHANGE_PATTERN.search(text):
        return "A future Moon phase change is not included in the facts."
    return ""


def check_grounding(text: str, facts: dict) -> tuple[bool, str]:
    """Return whether the text uses only fact-listed sky objects, directions, and numbers."""
    source = _fact_text(facts)
    allowed_objects = {name.lower() for name in facts.get("positions", {})}
    if facts.get("iss_passes"):
        allowed_objects.add("iss")
    if facts.get("sunset") or facts.get("dark_time"):
        allowed_objects.add("sun")

    found_objects = {
        term for term in CELESTIAL_TERMS
        if re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE)
    }
    aliases = {"international space station": "iss"}
    unknown_objects = sorted(
        term for term in found_objects
        if aliases.get(term, term) not in allowed_objects
    )
    if unknown_objects:
        return False, "Unlisted celestial object(s): " + ", ".join(unknown_objects)

    allowed_directions = {
        _canonical_direction(direction)
        for direction in DIRECTION_PATTERN.findall(source)
    }
    unknown_directions = sorted({
        direction for direction in DIRECTION_PATTERN.findall(text)
        if _canonical_direction(direction) not in allowed_directions
    })
    if unknown_directions:
        return False, "Direction(s) not present in the facts: " + ", ".join(unknown_directions)

    object_reason = _check_object_attributes(text, facts)
    if object_reason:
        return False, object_reason
    event_reason = _check_event_claims(text, facts)
    if event_reason:
        return False, event_reason

    allowed_times = {time.lower().replace(" ", "") for time in TIME_PATTERN.findall(source)}
    unknown_times = sorted({
        time for time in TIME_PATTERN.findall(text)
        if time.lower().replace(" ", "") not in allowed_times
    })
    if unknown_times:
        return False, "Time(s) not present in the facts: " + ", ".join(unknown_times)

    for match in re.finditer(r"\b(?:tonight|this evening)\b", text, re.IGNORECASE):
        nearby = text[max(0, match.start() - 45):match.end() + 45]
        morning_time = re.search(
            r"\b(?:0?[6-9]|1[01]):[0-5]\d\s?AM\b",
            nearby,
            re.IGNORECASE,
        )
        if morning_time:
            return "A morning time is described as happening tonight."

    allowed_numbers = {
        Decimal(number)
        for number in NUMBER_PATTERN.findall(TIME_PATTERN.sub("", source))
    }
    mentioned_numbers = NUMBER_PATTERN.findall(TIME_PATTERN.sub("", text))
    unknown_numbers = sorted({
        number for number in mentioned_numbers
        if Decimal(number) not in allowed_numbers
    })
    if unknown_numbers:
        return False, "Number(s) not present in the facts: " + ", ".join(unknown_numbers)

    allowed_number_words = {
        word.lower() for word in NUMBER_WORD_PATTERN.findall(source)
    }
    unknown_number_words = sorted({
        word.lower() for word in NUMBER_WORD_PATTERN.findall(text)
        if word.lower() not in allowed_number_words
    })
    if unknown_number_words:
        return False, "Number word(s) not present in the facts: " + ", ".join(unknown_number_words)

    unsupported_claims = sorted({
        word.lower() for word in UNSUPPORTED_CLAIM_PATTERN.findall(text)
        if word.lower() not in source.lower()
    })
    if unsupported_claims:
        return False, "Unverified visual or movement claim(s): " + ", ".join(unsupported_claims)
    return True, ""


def append_slip(text: str, reason: str) -> None:
    """Record a failed grounding check for later review."""
    with SLIP_LOG.open("a", encoding="utf-8") as log_file:
        log_file.write(f"Reason: {reason}\nText: {text}\n\n")
