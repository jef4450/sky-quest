"""Build a printable, offline Sky Quest card."""

import argparse
import json
import math
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import config
from html_cards import render_html_card
from narrate import narrate
from scorer import score_night
from sky import (
    compass_direction,
    find_iss_passes,
    get_positions,
    get_sky,
    is_dark_at,
    height_word,
    load_sky_data,
    localize,
    moon_illumination_at,
)
from deep_sky_targets import (
    get_telescope_target_positions,
    passes_telescope_conditions,
)
from constellation_guides import GUIDES, applicable_guides
from stars import BRIGHT_STARS, brightest_visible_stars, get_star_positions


DEMO_TIME = datetime(2026, 10, 15, 18, 0)
DEMO_LATITUDE = 0.0
DEMO_LONGITUDE = 0.0
PROJECT_DIR = Path(__file__).resolve().parent
STOP_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
MAX_JUVIA_ROWS = 5
MODE_PERSONAS = {"lucy": "calm", "juvia": "quiet", "natsu": "coach"}


def _format_time(when: datetime) -> str:
    return when.strftime("%I:%M %p").lstrip("0")


def _narration_facts(
    best_window: dict | None,
    sky_facts: dict,
    iss_passes: list,
    star_positions: dict | None = None,
    guides: list[dict] | None = None,
) -> dict:
    facts = {
        "best_window": (
            {
                "start": _format_time(best_window["start"]),
                "end": _format_time(best_window["end"]),
                "reasons": best_window["reasons"],
            }
            if best_window and best_window.get("start")
            else None
        ),
        "positions": sky_facts["positions"],
        "moon_phase": sky_facts["moon_phase"],
        "moonrise": sky_facts["moonrise"],
        "moonset": sky_facts["moonset"],
        "sunset": sky_facts["sunset"],
        "dark_time": sky_facts["dark_time"],
        "iss_passes": iss_passes,
    }
    if star_positions is not None:
        facts["stars"] = star_positions
    if guides is not None:
        facts["constellation_guides"] = guides
    return facts


def _window_text(best_window: dict | None) -> str:
    if not best_window or best_window.get("window_start") is None:
        return "No usable dark window found."
    return (
        f"{_format_time(best_window['window_start'])} to "
        f"{_format_time(best_window['window_end'])}"
    )


def _object_line(name: str, position: dict) -> dict:
    if not position["above_horizon"]:
        return {
            "text": f"{name}: below the horizon",
            "visible": False,
            "checkable": False,
        }
    return {
        "text": f"{name}: {position['direction']}, {position['height']}, above the horizon",
        "visible": True,
        "checkable": True,
    }


def _valid_best_window(best_window: dict | None) -> bool:
    """Reject incomplete or internally inconsistent scorer results."""
    if not best_window:
        return False
    start = best_window.get("window_start")
    end = best_window.get("window_end")
    positions = best_window.get("positions")
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        return False
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        return False
    if (end - start) != timedelta(minutes=config.BEST_WINDOW_MINUTES):
        return False
    if not isinstance(positions, dict):
        return False
    for name in ("Moon", "Jupiter", "Saturn"):
        position = positions.get(name)
        if not isinstance(position, dict):
            return False
        altitude = position.get("altitude_degrees")
        if (
            isinstance(altitude, bool)
            or not isinstance(altitude, (int, float))
            or not math.isfinite(altitude)
            or not -90 <= altitude <= 90
            or position.get("above_horizon") != (altitude > 0)
            or position.get("height") != height_word(altitude)
        ):
            return False
    return True


def _lucy_checklist(sky_facts: dict) -> list[dict]:
    return [
        _object_line(name, sky_facts["positions"][name])
        for name in ("Moon", "Jupiter", "Saturn")
    ]


def _polaris_item(star_positions: dict) -> dict:
    polaris = star_positions["Polaris"]
    altitude = polaris["altitude_degrees"]
    if not polaris["above_horizon"]:
        return {
            "text": "Polaris is not visible from this latitude",
            "visible": False,
            "checkable": False,
        }
    if altitude <= 15:
        return {
            "text": "Polaris is low from here: you need a clear north horizon.",
            "visible": True,
            "checkable": False,
        }
    return {
        "text": f"Polaris: {polaris['direction']}, {polaris['height']}",
        "visible": True,
        "checkable": True,
    }


_COMPASS_BEARINGS = {
    "north": 0.0,
    "north-east": 45.0,
    "east": 90.0,
    "south-east": 135.0,
    "south": 180.0,
    "south-west": 225.0,
    "west": 270.0,
    "north-west": 315.0,
}


def _window_bearing(facing: str | float | int | None) -> float | None:
    if facing is None:
        return None
    if isinstance(facing, str):
        return _COMPASS_BEARINGS[facing.lower()]
    return float(facing) % 360


def _position_azimuth(position: dict) -> float:
    if "azimuth_degrees" in position:
        return float(position["azimuth_degrees"])
    return _COMPASS_BEARINGS[position["direction"].lower()]


def _in_azimuth_window(position: dict, bearing: float | None, field_of_view: float) -> bool:
    if bearing is None:
        return True
    difference = abs(_position_azimuth(position) - bearing) % 360
    return min(difference, 360 - difference) <= field_of_view / 2


def _juvia_in_window(
    position: dict,
    facing: str | float | int | None,
    field_of_view: float,
    minimum_altitude: float,
) -> bool:
    if not position.get("above_horizon", False):
        return False
    bearing = _window_bearing(facing)
    if bearing is None:
        return True
    if position["altitude_degrees"] <= minimum_altitude:
        return False
    return _in_azimuth_window(position, bearing, field_of_view)


def _juvia_timeline(
    dark_start: datetime | None,
    ephemeris,
    timescale,
    lat: float,
    lon: float,
    iss_passes: list[dict],
    facing: str | float | int | None,
    field_of_view: float,
    minimum_altitude: float,
    include_telescope: bool = True,
) -> tuple[list[dict], dict]:
    """Calculate a capped hourly timeline of objects and guides in Juvia's window."""
    if dark_start is None:
        return [], {"timeline": [], "narration_line": "No dark timeline is available."}

    start = localize(dark_start)
    midnight = datetime.combine(
        start.date() + timedelta(days=1),
        time.min,
        tzinfo=start.tzinfo,
    )
    passes_by_start: list[tuple[datetime, dict]] = []
    for iss_pass in iss_passes:
        stamp = iss_pass.get("start_datetime")
        if stamp:
            pass_time = localize(datetime.fromisoformat(stamp))
        else:
            try:
                parsed = datetime.strptime(
                    iss_pass["start"], "%b %d, %I:%M %p"
                ).replace(year=start.year, tzinfo=start.tzinfo)
            except (KeyError, ValueError):
                continue
            if parsed < start:
                parsed = parsed.replace(year=parsed.year + 1)
            pass_time = parsed
        if start <= pass_time < midnight:
            passes_by_start.append((pass_time, iss_pass))

    rows = []
    facts_rows = []
    row_time = start
    for _ in range(MAX_JUVIA_ROWS):
        if row_time >= midnight:
            break
        next_row_time = min(row_time + timedelta(hours=1), midnight)
        planet_positions = get_positions(
            lat, lon, row_time, ephemeris, timescale
        )
        star_positions = get_star_positions(
            lat, lon, row_time, ephemeris, timescale
        )
        items = []
        fact_positions = {}
        fact_stars = {}
        target_positions = (
            get_telescope_target_positions(
                lat, lon, row_time, ephemeris, timescale
            )
            if include_telescope
            else {}
        )
        sky_is_dark = is_dark_at(
            lat, lon, row_time, ephemeris=ephemeris, timescale=timescale
        )
        moon_illumination = moon_illumination_at(
            ephemeris, timescale, row_time
        )

        for name in ("Moon", "Jupiter", "Saturn"):
            position = planet_positions[name]
            if not position["above_horizon"]:
                items.append(
                    {"text": f"{name}: below the horizon", "checkable": False}
                )
            elif not _juvia_in_window(
                position, facing, field_of_view, minimum_altitude
            ):
                items.append(
                    {"text": f"{name}: not in your window", "checkable": False}
                )
            else:
                items.append(
                    {
                        "text": (
                            f"{name}: {position['direction']}, {position['height']}"
                        ),
                        "checkable": True,
                    }
                )
                fact_positions[name] = position

        stars_in_window = {
            name: position
            for name, position in star_positions.items()
            if name in BRIGHT_STARS
            and name != "Polaris"
            and _juvia_in_window(
                position, facing, field_of_view, minimum_altitude
            )
        }
        bright_stars = brightest_visible_stars(stars_in_window, limit=5)
        for star in bright_stars:
            name = star["name"]
            position = star_positions[name]
            items.append(
                {
                    "text": f"{name}: {star['direction']}, {star['height']}",
                    "checkable": True,
                }
            )
            fact_stars[name] = position

        polaris = star_positions["Polaris"]
        if not polaris["above_horizon"]:
            items.append(
                {
                    "text": "Polaris is not visible from this latitude",
                    "checkable": False,
                }
            )
        elif not _juvia_in_window(
            polaris, facing, field_of_view, minimum_altitude
        ):
            items.append(
                {"text": "Polaris: not in your window", "checkable": False}
            )
        elif polaris["altitude_degrees"] <= 15:
            items.append(
                {
                    "text": "Polaris is low from here: you need a clear north horizon.",
                    "checkable": False,
                }
            )
            fact_stars["Polaris"] = polaris
        elif _juvia_in_window(
            polaris, facing, field_of_view, minimum_altitude
        ):
            items.append(
                {
                    "text": f"Polaris: {polaris['direction']}, {polaris['height']}",
                    "checkable": True,
                }
            )
            fact_stars["Polaris"] = polaris
        else:
            items.append(
                {"text": "Polaris: not in your window", "checkable": False}
            )

        in_window_anchors = {
            name: position
            for name, position in star_positions.items()
            if _juvia_in_window(
                position, facing, field_of_view, minimum_altitude
            )
        }
        guides = applicable_guides(in_window_anchors)
        for guide in guides:
            items.append(
                {
                    "text": guide["text"],
                    "checkable": True,
                    "guide": guide["name"],
                }
            )
            for anchor in next(
                entry["anchors"] for entry in GUIDES
                if entry["name"] == guide["name"]
            ):
                fact_stars[anchor] = star_positions[anchor]

        telescope_candidates = []
        best_by_kind = {}
        for target in target_positions.values():
            if (
                not _juvia_in_window(
                    target, facing, field_of_view, minimum_altitude
                )
                or target["altitude_degrees"] < 15
                or not passes_telescope_conditions(
                    target, planet_positions["Moon"], moon_illumination, sky_is_dark
                )
            ):
                continue
            current = best_by_kind.get(target["kind"])
            if current is None or target["altitude_degrees"] > current["altitude_degrees"]:
                best_by_kind[target["kind"]] = target
        for kind in (
            "double star", "open cluster", "globular cluster", "nebula", "galaxy"
        ):
            target = best_by_kind.get(kind)
            if target is not None:
                candidate = {
                    "name": target["name"],
                    "catalog": target["catalog"],
                    "kind": kind,
                    "direction": target["direction"],
                    "height": target["height"],
                    "altitude_degrees": target["altitude_degrees"],
                }
                telescope_candidates.append(candidate)

        row_passes = [
            iss_pass
            for pass_time, iss_pass in passes_by_start
            if row_time <= pass_time < next_row_time
        ]
        has_window_content = (
            any(item["checkable"] for item in items)
            or bool(telescope_candidates)
        )
        row = {
            "time": _format_time(row_time),
            "items": items,
            "empty": not has_window_content,
            "iss_passes": row_passes,
            "telescope_targets": telescope_candidates,
        }
        rows.append(row)
        facts_rows.append(
            {
                "time": _format_time(row_time),
                "positions": fact_positions,
                "stars": fact_stars,
                "constellation_guides": guides,
                "telescope_targets": {
                    item["catalog"]: target_positions[item["catalog"]]
                    for item in telescope_candidates
                },
                "iss_passes": [
                    {
                        "start": item["start"],
                        "appears_from": item["appears_from"],
                        "disappears_toward": item["disappears_toward"],
                    }
                    for item in row_passes
                ],
            }
        )
        row_time += timedelta(hours=1)

    facts = {
        "timeline": facts_rows,
        "iss_passes": [
            {
                "start": item["start"],
                "appears_from": item["appears_from"],
                "disappears_toward": item["disappears_toward"],
            }
            for row in facts_rows
            for item in row["iss_passes"]
        ],
        "narration_line": "A quiet view from your window is ready.",
    }
    return rows, facts


def _load_stops(demo: bool) -> list[dict]:
    source = PROJECT_DIR / (
        "stops.example.json" if demo else "stops.local.json"
    )
    if not demo and not source.exists():
        source = PROJECT_DIR / "stops.example.json"
    try:
        entries = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("Could not read the stop file; no stops were loaded.")
        return []

    if not isinstance(entries, list):
        print("Stop file must contain a list; no stops were loaded.")
        return []

    valid_stops = []
    required = {"name", "latitude", "longitude", "time"}
    for index, entry in enumerate(entries, start=1):
        reason = ""
        if not isinstance(entry, dict) or set(entry) != required:
            reason = "expected name, latitude, longitude, and time fields"
        elif not isinstance(entry["name"], str) or not entry["name"].strip():
            reason = "name must be a non-empty string"
        elif (
            isinstance(entry["latitude"], bool)
            or not isinstance(entry["latitude"], (int, float))
            or not -90 <= entry["latitude"] <= 90
            or not math.isfinite(entry["latitude"])
        ):
            reason = "latitude must be a number from -90 to 90"
        elif (
            isinstance(entry["longitude"], bool)
            or not isinstance(entry["longitude"], (int, float))
            or not -180 <= entry["longitude"] <= 180
            or not math.isfinite(entry["longitude"])
        ):
            reason = "longitude must be a number from -180 to 180"
        elif not isinstance(entry["time"], str) or not STOP_TIME_PATTERN.fullmatch(entry["time"]):
            reason = "time must use 24-hour HH:MM"

        if reason:
            print(f"Skipping invalid stop entry {index}: {reason}.")
            continue
        valid_stops.append(entry)
    return valid_stops


def _stop_datetime(
    date_anchor: datetime,
    time_text: str,
    reference_time: datetime,
) -> datetime:
    """Interpret a planned local clock time as tonight, rolling past times forward."""
    hour, minute = map(int, time_text.split(":"))
    planned = datetime.combine(date_anchor.date(), time(hour, minute))
    if planned <= reference_time.replace(tzinfo=None):
        planned += timedelta(days=1)
    return planned.replace(tzinfo=date_anchor.tzinfo)


def _natsu_stops(
    stops: list[dict],
    date_anchor: datetime,
    reference_time: datetime,
    ephemeris,
    timescale,
) -> tuple[list[dict], dict, list[dict]]:
    stop_records = []
    route_passes: dict[tuple, dict] = {}
    previous_stop_time = None
    for index, stop in enumerate(stops, start=1):
        when = _stop_datetime(date_anchor, stop["time"], reference_time)
        while previous_stop_time is not None and when <= previous_stop_time:
            when += timedelta(days=1)
        previous_stop_time = when

        is_dark = is_dark_at(
            stop["latitude"],
            stop["longitude"],
            when,
            ephemeris=ephemeris,
            timescale=timescale,
        )
        positions = (
            get_positions(
                stop["latitude"],
                stop["longitude"],
                when,
                ephemeris,
                timescale,
            )
            if is_dark
            else {}
        )
        star_positions = (
            get_star_positions(
                stop["latitude"],
                stop["longitude"],
                when,
                ephemeris,
                timescale,
            )
            if is_dark
            else {}
        )
        for iss_pass in find_iss_passes(
            stop["latitude"],
            stop["longitude"],
            when,
            ephemeris=ephemeris,
            timescale=timescale,
        ):
            key = (
                iss_pass["start"],
                iss_pass["appears_from"],
                iss_pass["disappears_toward"],
            )
            route_passes[key] = iss_pass
        visible = [
            (name, position)
            for name, position in {
                **positions,
                **{
                    name: star_positions[name]
                    for name in BRIGHT_STARS
                    if name in star_positions
                },
            }.items()
            if position["above_horizon"]
        ]
        if not is_dark:
            status = "sky not dark yet at this stop"
            target = None
        elif visible:
            name, position = max(
                visible,
                key=lambda candidate: candidate[1]["altitude_degrees"],
            )
            status = ""
            target = {
                "object": name,
                "direction": position["direction"],
                "height": position["height"],
            }
        else:
            status = "nothing above the horizon at this stop"
            target = None

        stop_records.append(
            {
                "number": index,
                "name": stop["name"],
                "when": when,
                "time": _format_time(when),
                "date": (
                    when.strftime("%b %d, %Y")
                ),
                "target": target,
                "status": status,
            }
        )

    route_facts = {
        "route_stops": [
            {
                "name": stop["name"],
                "date": stop["date"],
                "time": stop["time"],
                "target": stop["target"],
                "status": stop["status"],
            }
            for stop in stop_records
        ],
        "narration_line": "The planned route is ready.",
    }
    return (
        stop_records,
        route_facts,
        list(route_passes.values()),
    )


def _route_span(stops: list[dict], date_anchor: datetime) -> str:
    if not stops:
        return f"Route ({config.TIMEZONE}): no valid stops"
    first = stops[0]["when"]
    last = stops[-1]["when"]
    first_date = first.strftime("%b %d, %Y")
    if first.date() == last.date():
        span = f"{first_date}, {_format_time(first)} to {_format_time(last)}"
    else:
        span = (
            f"{first_date}, {_format_time(first)} to "
            f"{last.strftime('%b %d, %Y')}, {_format_time(last)}"
        )
    return f"Route ({config.TIMEZONE}): {span}"


def print_card(
    lat: float,
    lon: float,
    when: datetime,
    mode: str = "lucy",
    demo: bool = False,
    output_dir: Path | None = None,
    *,
    stops_override: list[dict] | None = None,
    window_settings: dict | None = None,
    equipment: str = "telescope",
    result_data: dict | None = None,
    place_label: str | None = None,
) -> Path:
    """Calculate shared sky facts and write one mode-specific HTML card."""
    if mode not in MODE_PERSONAS:
        raise ValueError("mode must be lucy, juvia, or natsu")

    ephemeris, timescale = load_sky_data()
    config._validate_window_settings()
    best_window = None
    sky_facts = None
    iss_passes = []
    facts = None
    if mode != "natsu":
        sky_facts = get_sky(
            lat, lon, when, ephemeris=ephemeris, timescale=timescale
        )
        iss_passes = find_iss_passes(
            lat,
            lon,
            when,
            ephemeris=ephemeris,
            timescale=timescale,
        )
        if mode == "lucy" and sky_facts["dark_start"] is not None:
            best_window = score_night(
                lat,
                lon,
                datetime.fromisoformat(sky_facts["dark_start"]),
                sky_facts["moon_illumination"],
                iss_passes,
                ephemeris,
                timescale,
            )
            if not _valid_best_window(best_window):
                best_window = None
        if mode == "lucy" and best_window is not None:
            sky_facts["positions"] = best_window["positions"]
        if mode == "lucy":
            facts = _narration_facts(best_window, sky_facts, iss_passes)
    card_data = {
        "title": {"lucy": "Lucy's Night Card", "juvia": "Juvia's Window Card",
                  "natsu": "Natsu's Run Card"}[mode],
        "date": when.strftime("%A, %B %d, %Y").replace(" 0", " "),
        "place_label": place_label if place_label is not None else config.PLACE_LABEL,
        "iss_passes": iss_passes,
    }
    if mode == "lucy":
        card_data["window_text"] = _window_text(best_window)

    persona = MODE_PERSONAS[mode]
    if mode == "lucy":
        assert sky_facts is not None and facts is not None
        observation_time = when
        if best_window and best_window.get("window_start") is not None:
            observation_time = best_window["window_start"] + (
                best_window["window_end"] - best_window["window_start"]
            ) / 2
        star_positions = get_star_positions(
            lat, lon, observation_time, ephemeris, timescale
        )
        guides = applicable_guides(star_positions)
        card_data["checklist"] = _lucy_checklist(sky_facts)
        card_data["stars"] = brightest_visible_stars(star_positions)
        card_data["polaris"] = _polaris_item(star_positions)
        card_data["guides"] = guides
        facts = _narration_facts(
            best_window,
            sky_facts,
            iss_passes,
            star_positions,
            guides,
        )
        card_data["intro"] = narrate(
            facts,
            persona,
            sentence_count=2,
            validate_sentence_count=True,
            deterministic=demo,
        )
    elif mode == "juvia":
        dark_start = (
            datetime.fromisoformat(sky_facts["dark_start"])
            if sky_facts and sky_facts.get("dark_start")
            else None
        )
        settings = window_settings or {}
        facing = settings.get("facing", config.WINDOW_FACING)
        field_of_view = settings.get(
            "field_of_view", config.WINDOW_FIELD_OF_VIEW
        )
        minimum_altitude = settings.get(
            "minimum_altitude", config.WINDOW_MIN_ALTITUDE
        )
        bearing = _window_bearing(facing)
        card_data["window_facing"] = (
            f"{facing.lower()}"
            if isinstance(facing, str)
            else (
                f"{facing:g}° ({compass_direction(bearing)})"
                if bearing is not None
                else None
            )
        )
        timeline, timeline_facts = _juvia_timeline(
            dark_start,
            ephemeris,
            timescale,
            lat,
            lon,
            iss_passes,
            facing,
            field_of_view,
            minimum_altitude,
            include_telescope=equipment == "telescope",
        )
        card_data["timeline"] = timeline
        card_data["equipment"] = equipment
        card_data["iss_passes"] = [
            item for row in timeline for item in row["iss_passes"]
        ]
        card_data["intro"] = (
            "Telescope candidates pass the altitude, darkness, and Moon checks "
            "shown here; local sky conditions still affect what you can see."
            if equipment == "telescope"
            else "Take a quiet naked-eye look at the objects listed in your window."
        )
        facts = {
            "sky": sky_facts,
            **timeline_facts,
        }
    else:
        uses_example_stops = (
            stops_override is None
            and (demo or not (PROJECT_DIR / "stops.local.json").is_file())
        )
        stops = stops_override if stops_override is not None else _load_stops(demo)
        card_data["stops"], route_facts, route_passes = _natsu_stops(
            stops, when, when, ephemeris, timescale
        )
        card_data["route_text"] = _route_span(card_data["stops"], when)
        card_data["stops_label"] = (
            "Demo placeholders - fictional sample stops"
            if demo
            else (
                "Example placeholders - stops.local.json was not found"
                if uses_example_stops
                else "Configured route stops"
            )
        )
        card_data["iss_passes"] = route_passes
        card_data["intro"] = narrate(
            route_facts,
            persona,
            sentence_count=1,
            validate_sentence_count=True,
            deterministic=demo,
        )
        facts = route_facts

    html = render_html_card(mode, card_data)
    if result_data is not None:
        result_data["html"] = html
        result_data["facts"] = facts
    destination_dir = output_dir or PROJECT_DIR / "cards"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{mode}-{when:%Y-%m-%d}.html"
    destination.write_text(html, encoding="utf-8")
    print(f"HTML card saved to cards/{destination.name}")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a printable Sky Quest card.")
    parser.add_argument(
        "--mode",
        choices=tuple(MODE_PERSONAS),
        default="lucy",
        help="Choose Lucy's relaxed, Juvia's window, or Natsu's running card.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use fixed sample date and fictional sample locations.",
    )
    args = parser.parse_args(argv)

    if args.demo:
        latitude, longitude = DEMO_LATITUDE, DEMO_LONGITUDE
        when = DEMO_TIME.replace(tzinfo=ZoneInfo(config.TIMEZONE))
    else:
        if config.LATITUDE is None or config.LONGITUDE is None:
            parser.error(
                "Set SKY_QUEST_LATITUDE and SKY_QUEST_LONGITUDE before running."
            )
        latitude, longitude = config.LATITUDE, config.LONGITUDE
        when = localize(datetime.now(ZoneInfo(config.TIMEZONE)))

    try:
        print_card(latitude, longitude, when, mode=args.mode, demo=args.demo)
    except (FileNotFoundError, ValueError, OSError):
        print("Sky Quest could not build the card. Check the local data files and settings.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
