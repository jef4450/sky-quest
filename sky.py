"""Offline sky calculations using the saved Skyfield ephemeris and ISS TLE."""

from datetime import date, datetime, time, timedelta
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from skyfield.api import EarthSatellite, load, load_file, wgs84
from skyfield import almanac

import config


DATA_DIR = Path(__file__).resolve().parent / "data"
PLANET_FILE = DATA_DIR / "de421.bsp"
ISS_FILE = DATA_DIR / "iss.tle"
PLANETS = (("Moon", "moon"), ("Jupiter", "jupiter barycenter"), ("Saturn", "saturn barycenter"))
DARK_SUN_ALTITUDE = -18.0


def localize(when: datetime) -> datetime:
    """Return a timezone-aware datetime in the configured local timezone."""
    timezone = ZoneInfo(config.TIMEZONE)
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone)
    return when.astimezone(timezone)


def load_sky_data():
    """Open only the local planetary file and use Skyfield's built-in time data."""
    if not PLANET_FILE.is_file():
        raise FileNotFoundError(
            f"Missing {PLANET_FILE}. With internet access, run: python download_data.py"
        )
    ephemeris = load_file(str(PLANET_FILE))
    timescale = load.timescale(builtin=True)
    return ephemeris, timescale


def load_iss_satellite(timescale):
    """Read the saved ISS two-line element set without contacting a server."""
    if not ISS_FILE.is_file():
        raise FileNotFoundError(
            f"Missing {ISS_FILE}. With internet access, run: python download_data.py"
        )
    lines = [line.strip() for line in ISS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    line_one = next((line for line in lines if line.startswith("1 ")), None)
    line_two = next((line for line in lines if line.startswith("2 ")), None)
    if line_one is None or line_two is None:
        raise ValueError(f"{ISS_FILE} does not contain a valid ISS TLE.")
    return EarthSatellite(line_one, line_two, "ISS (ZARYA)", timescale)


def compass_direction(azimuth_degrees: float) -> str:
    """Convert an azimuth (clockwise from north) to one of eight directions."""
    directions = (
        "north", "north-east", "east", "south-east",
        "south", "south-west", "west", "north-west",
    )
    return directions[int((azimuth_degrees + 22.5) // 45) % 8]


def height_word(altitude_degrees: float) -> str:
    """Describe an object's altitude in simple terms."""
    if altitude_degrees < 30:
        return "low"
    if altitude_degrees < 60:
        return "halfway up"
    return "high"


def _position(observer, body, sky_time) -> dict:
    apparent = observer.at(sky_time).observe(body).apparent()
    altitude, azimuth, _ = apparent.altaz()
    altitude_degrees = float(altitude.degrees)
    return {
        "altitude_degrees": round(altitude_degrees, 1),
        "direction": compass_direction(float(azimuth.degrees)),
        "height": height_word(altitude_degrees),
        "above_horizon": altitude_degrees > 0,
    }


def get_positions(lat: float, lon: float, when: datetime, ephemeris, timescale) -> dict:
    """Calculate the Moon, Jupiter, and Saturn positions for one moment."""
    moment = localize(when)
    observer = ephemeris["earth"] + wgs84.latlon(latitude_degrees=lat, longitude_degrees=lon)
    sky_time = timescale.from_datetime(moment)
    return {
        name: _position(observer, ephemeris[body_key], sky_time)
        for name, body_key in PLANETS
    }


def _event_times(ephemeris, timescale, observer, start_local: datetime, end_local: datetime, finder):
    start = timescale.from_datetime(start_local)
    end = timescale.from_datetime(end_local)
    event_times, event_values = almanac.find_discrete(start, end, finder(ephemeris, observer))
    return [
        (moment.utc_datetime().astimezone(start_local.tzinfo), bool(value))
        for moment, value in zip(event_times, event_values)
    ]


def _dark_start(ephemeris, timescale, observer, start_local: datetime, end_local: datetime):
    """Find the evening crossing below -18 degrees, to roughly one-minute precision."""
    sun = ephemeris["sun"]
    current = start_local
    current_altitude = _sun_altitude(observer, sun, timescale.from_datetime(current))
    while current < end_local:
        following = min(current + timedelta(minutes=10), end_local)
        following_altitude = _sun_altitude(observer, sun, timescale.from_datetime(following))
        if current_altitude > DARK_SUN_ALTITUDE >= following_altitude:
            low, high = current, following
            while (high - low).total_seconds() > 60:
                middle = low + (high - low) / 2
                middle_altitude = _sun_altitude(observer, sun, timescale.from_datetime(middle))
                if middle_altitude <= DARK_SUN_ALTITUDE:
                    high = middle
                else:
                    low = middle
            return high
        current, current_altitude = following, following_altitude
    return None


def _sun_altitude(observer, sun, sky_time) -> float:
    apparent = observer.at(sky_time).observe(sun).apparent()
    return float(apparent.altaz()[0].degrees)


def _moon_phase(phase_degrees: float) -> str:
    phases = (
        "new moon", "waxing crescent", "first quarter", "waxing gibbous",
        "full moon", "waning gibbous", "last quarter", "waning crescent",
    )
    index = int((phase_degrees + 22.5) // 45) % 8
    return phases[index]


def _clock(when: datetime | None) -> str | None:
    return when.strftime("%I:%M %p").lstrip("0") if when is not None else None


def get_sky(
    lat: float,
    lon: float,
    when: datetime,
    *,
    ephemeris=None,
    timescale=None,
) -> dict:
    """Return positions and local observing times calculated from saved data."""
    if ephemeris is None or timescale is None:
        ephemeris, timescale = load_sky_data()

    moment = localize(when)
    timezone = moment.tzinfo
    local_midnight = datetime.combine(moment.date(), time.min, tzinfo=timezone)
    next_midnight = local_midnight + timedelta(days=1)
    topos = wgs84.latlon(latitude_degrees=lat, longitude_degrees=lon)
    observer = ephemeris["earth"] + topos

    moon_events = _event_times(
        ephemeris, timescale, topos, local_midnight, next_midnight,
        lambda eph, place: almanac.risings_and_settings(eph, eph["moon"], place),
    )
    sun_events = _event_times(
        ephemeris, timescale, topos, local_midnight, next_midnight,
        almanac.sunrise_sunset,
    )
    moon = _position(observer, ephemeris["moon"], timescale.from_datetime(moment))
    phase_degrees = float(almanac.moon_phase(ephemeris, timescale.from_datetime(moment)).degrees)
    dark_start = _dark_start(ephemeris, timescale, observer, local_midnight, next_midnight)

    moonrise = next((event for event, is_rising in moon_events if is_rising), None)
    moonset = next((event for event, is_rising in moon_events if not is_rising), None)
    sunset = next((event for event, is_sunrise in sun_events if not is_sunrise), None)
    return {
        "when": moment.strftime("%Y-%m-%d %I:%M %p").lstrip("0"),
        "positions": {
            "Moon": moon,
            "Jupiter": _position(observer, ephemeris["jupiter barycenter"], timescale.from_datetime(moment)),
            "Saturn": _position(observer, ephemeris["saturn barycenter"], timescale.from_datetime(moment)),
        },
        "moon_phase": _moon_phase(phase_degrees),
        "moon_illumination": round((1 - math.cos(math.radians(phase_degrees))) / 2, 2),
        "moonrise": _clock(moonrise),
        "moonset": _clock(moonset),
        "sunset": _clock(sunset),
        "dark_time": _clock(dark_start),
        "dark_start": dark_start.isoformat() if dark_start is not None else None,
    }


def _sun_is_dark(observer, sun, sky_time) -> bool:
    return _sun_altitude(observer, sun, sky_time) <= DARK_SUN_ALTITUDE


def find_iss_passes(
    lat: float,
    lon: float,
    when: datetime,
    *,
    ephemeris=None,
    timescale=None,
) -> list[dict]:
    """Find ISS passes that are above the horizon, sunlit, and in a dark sky."""
    if ephemeris is None or timescale is None:
        ephemeris, timescale = load_sky_data()
    satellite = load_iss_satellite(timescale)
    moment = localize(when)
    timezone = moment.tzinfo
    local_midnight = datetime.combine(moment.date(), time.min, tzinfo=timezone)
    next_midnight = local_midnight + timedelta(days=1)
    observer = ephemeris["earth"] + wgs84.latlon(latitude_degrees=lat, longitude_degrees=lon)
    dark_start = _dark_start(ephemeris, timescale, observer, local_midnight, next_midnight)
    if dark_start is None:
        return []

    scan_end = next_midnight + timedelta(hours=12)
    step = timedelta(seconds=30)
    satellite_difference = satellite - wgs84.latlon(
        latitude_degrees=lat, longitude_degrees=lon
    )
    samples = []
    sample_time = dark_start
    while sample_time < scan_end:
        sky_time = timescale.from_datetime(sample_time)
        satellite_position = satellite.at(sky_time)
        topocentric = satellite_difference.at(sky_time)
        altitude, azimuth, _ = topocentric.altaz()
        visible = (
            float(altitude.degrees) > 0
            and satellite_position.is_sunlit(ephemeris)
            and _sun_is_dark(observer, ephemeris["sun"], sky_time)
        )
        samples.append(
            (sample_time, visible, float(altitude.degrees), float(azimuth.degrees))
        )
        sample_time += step

    passes = []
    current = []
    for sample in samples:
        if sample[1]:
            current.append(sample)
        elif current:
            summary = _summarize_pass(current)
            if summary is not None:
                passes.append(summary)
            current = []
    if current:
        summary = _summarize_pass(current)
        if summary is not None:
            passes.append(summary)
    return passes


def _summarize_pass(samples: list[tuple]) -> dict | None:
    first, last = samples[0], samples[-1]
    peak = max(samples, key=lambda sample: sample[2])
    if peak[2] < 10:
        return None
    return {
        "start": first[0].strftime("%b %d, %I:%M %p").lstrip("0"),
        "appears_from": compass_direction(first[3]),
        "disappears_toward": compass_direction(last[3]),
        "duration_minutes": round(
            ((last[0] - first[0]).total_seconds() + 30) / 60, 1
        ),
        "peak_altitude_degrees": round(peak[2], 1),
        "peak_height": height_word(peak[2]),
    }
