"""One-off online check of stars.py coordinates against Hipparcos."""

from pathlib import Path

from skyfield.api import Loader
from skyfield.data import hipparcos

from stars import STAR_CATALOG


DATA_DIR = Path(__file__).resolve().parent / "data"
RA_TOLERANCE_HOURS = 0.00001
DEC_TOLERANCE_DEGREES = 0.0001
MAGNITUDE_TOLERANCE = 0.02


def main() -> int:
    DATA_DIR.mkdir(exist_ok=True)
    loader = Loader(str(DATA_DIR), verbose=False)
    try:
        with loader.open(hipparcos.URL) as catalog_file:
            catalog = hipparcos.load_dataframe(catalog_file)
    except OSError as error:
        print(f"Could not load the Hipparcos catalog: {error}")
        return 1

    headings = (
        f"{'Star':34} {'HIP':>7} {'Catalog RA (h)':>15} {'Catalog Dec (deg)':>18} "
        f"{'Catalog mag':>12} {'RA':>5} {'Dec':>5} {'Mag':>5} {'Result':>7}"
    )
    print(headings)
    print("-" * len(headings))
    failures = 0
    for name, record in STAR_CATALOG.items():
        hip = record["hip"]
        if hip not in catalog.index:
            ra_ok = dec_ok = magnitude_ok = False
            catalog_ra = catalog_dec = catalog_magnitude = float("nan")
        else:
            row = catalog.loc[hip]
            catalog_ra = float(row["ra_degrees"]) / 15.0
            catalog_dec = float(row["dec_degrees"])
            catalog_magnitude = float(row["magnitude"])
            ra_ok = abs(record["ra_hours"] - catalog_ra) <= RA_TOLERANCE_HOURS
            dec_ok = abs(record["dec_degrees"] - catalog_dec) <= DEC_TOLERANCE_DEGREES
            magnitude_ok = (
                abs(record["apparent_magnitude"] - catalog_magnitude)
                <= MAGNITUDE_TOLERANCE
            )
        passed = ra_ok and dec_ok and magnitude_ok
        failures += not passed
        print(
            f"{name:34} {hip:7d} {catalog_ra:15.6f} {catalog_dec:18.6f} "
            f"{catalog_magnitude:12.2f} {('PASS' if ra_ok else 'FAIL'):>5} "
            f"{('PASS' if dec_ok else 'FAIL'):>5} "
            f"{('PASS' if magnitude_ok else 'FAIL'):>5} "
            f"{('PASS' if passed else 'FAIL'):>7}"
        )
    print(f"\n{len(STAR_CATALOG) - failures}/{len(STAR_CATALOG)} stars passed.")
    print("Hipparcos data is cached in the Git-ignored data/ folder.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
