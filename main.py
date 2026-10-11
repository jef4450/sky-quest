"""Print tonight's plain-text Sky Quest card."""

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

import config
from narrate import narrate
from scorer import score_night
from sky import find_iss_passes, get_sky, load_sky_data, localize


DEMO_TIME = datetime(2026, 10, 15, 18, 0)
DEMO_LOCATION = (12.9716, 77.5946)  # Bengaluru, used only when --demo is selected.


def _format_position(name: str, position: dict) -> str:
    horizon = "above the horizon" if position["above_horizon"] else "below the horizon"
    return (
        f"{name}: {position['height']}, {position['direction']} "
        f"({position['altitude_degrees']} degrees; {horizon})"
    )


def _narration_facts(best_window: dict | None, sky_facts: dict, iss_passes: list) -> dict:
    return {
        "best_window": (
            {
                "start": best_window["start"].strftime("%I:%M %p").lstrip("0"),
                "end": best_window["end"].strftime("%I:%M %p").lstrip("0"),
                "reasons": best_window["reasons"],
            }
            if best_window else None
        ),
        "positions": sky_facts["positions"],
        "moon_phase": sky_facts["moon_phase"],
        "moonrise": sky_facts["moonrise"],
        "moonset": sky_facts["moonset"],
        "sunset": sky_facts["sunset"],
        "dark_time": sky_facts["dark_time"],
        "iss_passes": iss_passes,
    }


def print_card(lat: float, lon: float, when: datetime) -> None:
    ephemeris, timescale = load_sky_data()
    sky_facts = get_sky(
        lat, lon, when, ephemeris=ephemeris, timescale=timescale
    )
    iss_passes = find_iss_passes(
        lat, lon, when, ephemeris=ephemeris, timescale=timescale
    )

    best_window = None
    if sky_facts["dark_start"] is not None:
        best_window = score_night(
            lat,
            lon,
            datetime.fromisoformat(sky_facts["dark_start"]),
            sky_facts["moon_illumination"],
            iss_passes,
            ephemeris,
            timescale,
        )

    has_best_window = bool(best_window and best_window["window_start"] is not None)
    if has_best_window:
        sky_facts["positions"] = best_window["positions"]
    facts = _narration_facts(best_window if has_best_window else None, sky_facts, iss_passes)

    print("\nSKY QUEST - TONIGHT")
    print(f"Location: {lat:.4f}, {lon:.4f} ({config.TIMEZONE})")
    print(f"Moon: {sky_facts['moon_phase']}; rise {sky_facts['moonrise'] or 'not today'}, "
          f"set {sky_facts['moonset'] or 'not today'}")
    print(f"Sunset: {sky_facts['sunset'] or 'not today'}; properly dark: "
          f"{sky_facts['dark_time'] or 'not tonight'}")

    print("\nBEST WINDOW")
    if has_best_window:
        start = best_window["window_start"].strftime("%I:%M %p").lstrip("0")
        end = best_window["window_end"].strftime("%I:%M %p").lstrip("0")
        print(f"{start} to {end}")
        print(f"Score: {best_window['total_score']:g}")
        for reason in best_window["reasons"]:
            print(f"- {reason}")
    else:
        message = (
            best_window["message"]
            if best_window
            else "No dark window was found for this date."
        )
        print(message)

    print("\nWHAT IS WHERE (at the best window)")
    for name, position in sky_facts["positions"].items():
        print(_format_position(name, position))

    print("\nISS")
    if iss_passes:
        for iss_pass in iss_passes:
            print(
                f"{iss_pass['start']}: {iss_pass['appears_from']} to "
                f"{iss_pass['disappears_toward']}, {iss_pass['duration_minutes']} minutes, "
                f"peaks {iss_pass['peak_height']} "
                f"({iss_pass['peak_altitude_degrees']} degrees)"
            )
    else:
        print("No visible ISS passes found for this night.")

    print("\nTHREE THINGS TO FIND")
    for target in ("Moon", "Jupiter", "Saturn"):
        position = sky_facts["positions"][target]
        horizon = "above horizon" if position["above_horizon"] else "below horizon"
        print(f"[ ] {target} - {position['direction']} ({horizon})")

    print("\nGEMMA SAYS")
    print(narrate(facts))


def main() -> int:
    parser = argparse.ArgumentParser(description="Print an offline sky-planning card.")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use a fixed 2026 date and a sample Bengaluru location.",
    )
    args = parser.parse_args()

    if args.demo:
        latitude, longitude = DEMO_LOCATION
        when = DEMO_TIME.replace(tzinfo=ZoneInfo(config.TIMEZONE))
    else:
        if config.LATITUDE is None or config.LONGITUDE is None:
            parser.error("Set LATITUDE and LONGITUDE in config.py, or use --demo.")
        latitude, longitude = config.LATITUDE, config.LONGITUDE
        when = localize(datetime.now(ZoneInfo(config.TIMEZONE)))

    try:
        print_card(latitude, longitude, when)
    except (FileNotFoundError, ValueError, OSError) as error:
        print(f"Sky Quest could not build the card: {error}")
        print("Check the data files and location settings, then try again.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
