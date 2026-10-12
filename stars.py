"""Offline positions for bright stars and constellation guide anchors."""

from skyfield.api import Star, wgs84

from sky import compass_direction, height_word, localize


# Hipparcos ICRS right ascension is in hours; declination is in degrees.
BRIGHT_STARS = {
    "Polaris": {"ra_hours": 2.529743126, "dec_degrees": 89.264138050, "apparent_magnitude": 1.97, "hip": 11767},
    "Sirius": {"ra_hours": 6.752569403, "dec_degrees": -16.713143060, "apparent_magnitude": -1.44, "hip": 32349},
    "Vega": {"ra_hours": 18.615607221, "dec_degrees": 38.782993110, "apparent_magnitude": 0.03, "hip": 91262},
    "Arcturus": {"ra_hours": 14.261207602, "dec_degrees": 19.187269970, "apparent_magnitude": -0.05, "hip": 69673},
    "Betelgeuse": {"ra_hours": 5.919524774, "dec_degrees": 7.407036340, "apparent_magnitude": 0.45, "hip": 27989},
    "Rigel": {"ra_hours": 5.242297569, "dec_degrees": -8.201639190, "apparent_magnitude": 0.18, "hip": 24436},
    "Altair": {"ra_hours": 19.846300573, "dec_degrees": 8.867384910, "apparent_magnitude": 0.76, "hip": 97649},
    "Deneb": {"ra_hours": 20.690531513, "dec_degrees": 45.280334230, "apparent_magnitude": 1.25, "hip": 102098},
    "Capella": {"ra_hours": 5.278137678, "dec_degrees": 45.999029270, "apparent_magnitude": 0.08, "hip": 24608},
    "Aldebaran": {"ra_hours": 4.598666797, "dec_degrees": 16.509761640, "apparent_magnitude": 0.87, "hip": 21421},
    "Antares": {"ra_hours": 16.490129869, "dec_degrees": -26.431946080, "apparent_magnitude": 1.06, "hip": 80763},
    "Spica": {"ra_hours": 13.419890153, "dec_degrees": -11.161244910, "apparent_magnitude": 0.98, "hip": 65474},
    "Regulus": {"ra_hours": 10.139572050, "dec_degrees": 11.967195130, "apparent_magnitude": 1.36, "hip": 49669},
    "Procyon": {"ra_hours": 7.655149463, "dec_degrees": 5.227507670, "apparent_magnitude": 0.40, "hip": 37279},
    "Pollux": {"ra_hours": 7.755378842, "dec_degrees": 28.026310310, "apparent_magnitude": 1.16, "hip": 37826},
    "Fomalhaut": {"ra_hours": 22.960784882, "dec_degrees": -29.621837010, "apparent_magnitude": 1.17, "hip": 113368},
    "Canopus": {"ra_hours": 6.399191842, "dec_degrees": -52.695717990, "apparent_magnitude": -0.62, "hip": 30438},
    "Achernar": {"ra_hours": 1.628542136, "dec_degrees": -57.236660070, "apparent_magnitude": 0.45, "hip": 7588},
    "Alpha Centauri (Rigil Kentaurus)": {"ra_hours": 14.661360689, "dec_degrees": -60.835147070, "apparent_magnitude": -0.01, "hip": 71683},
    "Acrux": {"ra_hours": 12.443317057, "dec_degrees": -63.099055860, "apparent_magnitude": 0.77, "hip": 60718},
    "Hadar": {"ra_hours": 14.063734599, "dec_degrees": -60.372978400, "apparent_magnitude": 0.61, "hip": 68702},
    "Mimosa": {"ra_hours": 12.795366358, "dec_degrees": -59.688732460, "apparent_magnitude": 1.25, "hip": 62434},
    "Gacrux": {"ra_hours": 12.519424801, "dec_degrees": -57.112569220, "apparent_magnitude": 1.59, "hip": 61084},
}

# These additional catalog stars are used only to determine whether guides are up.
GUIDE_ANCHOR_STARS = {
    "Dubhe": {"ra_hours": 11.062176910, "dec_degrees": 61.751118880, "apparent_magnitude": 1.81, "hip": 54061},
    "Merak": {"ra_hours": 11.030664100, "dec_degrees": 56.382344780, "apparent_magnitude": 2.34, "hip": 53910},
    "Schedar": {"ra_hours": 0.675107566, "dec_degrees": 56.537409280, "apparent_magnitude": 2.24, "hip": 3179},
    "Caph": {"ra_hours": 0.152802691, "dec_degrees": 59.150218140, "apparent_magnitude": 2.28, "hip": 746},
}

STAR_CATALOG = {**BRIGHT_STARS, **GUIDE_ANCHOR_STARS}


def get_star_positions(
    lat: float,
    lon: float,
    when,
    ephemeris,
    timescale,
) -> dict[str, dict]:
    """Calculate the catalog and guide-anchor positions for one observer/time."""
    observer = ephemeris["earth"] + wgs84.latlon(
        latitude_degrees=lat,
        longitude_degrees=lon,
    )
    sky_time = timescale.from_datetime(localize(when))
    positions = {}
    for name, record in STAR_CATALOG.items():
        star = Star(
            ra_hours=record["ra_hours"],
            dec_degrees=record["dec_degrees"],
        )
        apparent = observer.at(sky_time).observe(star).apparent()
        altitude, azimuth, _ = apparent.altaz()
        altitude_degrees = round(float(altitude.degrees), 1)
        positions[name] = {
            "altitude_degrees": altitude_degrees,
            "azimuth_degrees": round(float(azimuth.degrees), 1),
            "direction": compass_direction(float(azimuth.degrees)),
            "height": height_word(altitude_degrees),
            "above_horizon": altitude_degrees > 0,
            "apparent_magnitude": record["apparent_magnitude"],
        }
    return positions


def brightest_visible_stars(
    positions: dict[str, dict],
    limit: int = 5,
) -> list[dict]:
    """Return the brightest above-horizon catalog stars, breaking ties by altitude."""
    visible = [
        {
            "name": name,
            "direction": positions[name]["direction"],
            "height": positions[name]["height"],
            "altitude_degrees": positions[name]["altitude_degrees"],
            "apparent_magnitude": record["apparent_magnitude"],
            "above_horizon": True,
        }
        for name, record in BRIGHT_STARS.items()
        if name in positions and positions[name]["above_horizon"]
    ]
    return sorted(
        visible,
        key=lambda star: (
            star["apparent_magnitude"],
            -star["altitude_degrees"],
        ),
    )[:limit]
