"""Small offline telescope-target catalog and local observing checks."""

import math

from skyfield.api import Star, wgs84

from sky import compass_direction, height_word, localize


# J2000 positions and object classes from the Messier/NGC and SIMBAD catalogs.
TARGET_CATALOG = (
    {"name": "Albireo", "catalog": "Beta Cygni", "kind": "double star", "ra_hours": 19.5119, "dec_degrees": 27.9597},
    {"name": "Mizar", "catalog": "Zeta Ursae Majoris", "kind": "double star", "ra_hours": 13.3988, "dec_degrees": 54.9254},
    {"name": "Epsilon Lyrae", "catalog": "Double Double", "kind": "double star", "ra_hours": 18.7389, "dec_degrees": 39.6700},
    {"name": "Pleiades", "catalog": "M 45", "kind": "open cluster", "ra_hours": 3.7900, "dec_degrees": 24.1167},
    {"name": "Beehive Cluster", "catalog": "M 44", "kind": "open cluster", "ra_hours": 8.6733, "dec_degrees": 19.6667},
    {"name": "Double Cluster", "catalog": "NGC 869/884", "kind": "open cluster", "ra_hours": 2.3333, "dec_degrees": 57.1500},
    {"name": "Hercules Cluster", "catalog": "M 13", "kind": "globular cluster", "ra_hours": 16.6948, "dec_degrees": 36.4611},
    {"name": "M 4", "catalog": "NGC 6121", "kind": "globular cluster", "ra_hours": 16.3931, "dec_degrees": -26.5250},
    {"name": "Sagittarius Cluster", "catalog": "M 22", "kind": "globular cluster", "ra_hours": 18.6067, "dec_degrees": -23.9000},
    {"name": "Orion Nebula", "catalog": "M 42", "kind": "nebula", "ra_hours": 5.5881, "dec_degrees": -5.3911},
    {"name": "Ring Nebula", "catalog": "M 57", "kind": "nebula", "ra_hours": 18.8931, "dec_degrees": 33.0300},
    {"name": "Lagoon Nebula", "catalog": "M 8", "kind": "nebula", "ra_hours": 18.0603, "dec_degrees": -24.3867},
    {"name": "Andromeda Galaxy", "catalog": "M 31", "kind": "galaxy", "ra_hours": 0.7123, "dec_degrees": 41.2692},
    {"name": "Bode's Galaxy", "catalog": "M 81", "kind": "galaxy", "ra_hours": 9.9259, "dec_degrees": 69.0653},
    {"name": "Whirlpool Galaxy", "catalog": "M 51", "kind": "galaxy", "ra_hours": 13.4979, "dec_degrees": 47.1952},
)

DEEP_SKY_KINDS = frozenset(
    {"open cluster", "globular cluster", "nebula", "galaxy"}
)
MIN_TELESCOPE_ALTITUDE = 15.0
MAX_MOON_ILLUMINATION = 0.25
MIN_MOON_SEPARATION = 45.0


def get_telescope_target_positions(
    latitude: float,
    longitude: float,
    when,
    ephemeris,
    timescale,
) -> dict[str, dict]:
    """Calculate local altitude and bearing for every bundled catalog target."""
    observer = ephemeris["earth"] + wgs84.latlon(
        latitude_degrees=latitude,
        longitude_degrees=longitude,
    )
    sky_time = timescale.from_datetime(localize(when))
    apparent_observer = observer.at(sky_time)
    positions = {}
    for target in TARGET_CATALOG:
        apparent = apparent_observer.observe(
            Star(
                ra_hours=target["ra_hours"],
                dec_degrees=target["dec_degrees"],
            )
        ).apparent()
        altitude, azimuth, _ = apparent.altaz()
        altitude_degrees = round(float(altitude.degrees), 1)
        positions[target["catalog"]] = {
            **target,
            "altitude_degrees": altitude_degrees,
            "azimuth_degrees": round(float(azimuth.degrees), 1),
            "direction": compass_direction(float(azimuth.degrees)),
            "height": height_word(altitude_degrees),
            "above_horizon": altitude_degrees > 0,
        }
    return positions


def angular_separation_degrees(first: dict, second: dict) -> float:
    """Calculate angular separation from two local altitude/azimuth positions."""
    first_alt = math.radians(first["altitude_degrees"])
    second_alt = math.radians(second["altitude_degrees"])
    azimuth_difference = math.radians(
        first["azimuth_degrees"] - second["azimuth_degrees"]
    )
    cosine = (
        math.sin(first_alt) * math.sin(second_alt)
        + math.cos(first_alt) * math.cos(second_alt) * math.cos(azimuth_difference)
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def passes_telescope_conditions(
    target: dict,
    moon: dict,
    moon_illumination: float,
    sky_is_dark: bool,
) -> bool:
    """Require darkness, useful altitude, and conservative Moon conditions."""
    if (
        not sky_is_dark
        or not target["above_horizon"]
        or target["altitude_degrees"] < MIN_TELESCOPE_ALTITUDE
    ):
        return False
    if target["kind"] not in DEEP_SKY_KINDS or not moon["above_horizon"]:
        return True
    return (
        moon_illumination <= MAX_MOON_ILLUMINATION
        and angular_separation_degrees(target, moon) >= MIN_MOON_SEPARATION
    )
