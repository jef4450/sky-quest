"""Download the astronomy files once, while an internet connection is available."""

from pathlib import Path
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen


DATA_DIR = Path(__file__).resolve().parent / "data"
DOWNLOADS = (
    (
        "JPL planetary ephemeris",
        "https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de421.bsp",
        DATA_DIR / "de421.bsp",
    ),
    (
        "current ISS orbit data",
        "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE",
        DATA_DIR / "iss.tle",
    ),
)


def download_file(label: str, url: str, destination: Path) -> bool:
    """Download one URL and save it only after a successful response."""
    temporary_path = destination.with_suffix(destination.suffix + ".part")
    request = Request(url, headers={"User-Agent": "SkyQuest/1.0"})

    try:
        with urlopen(request, timeout=60) as response:
            content = response.read()

        if destination.suffix == ".tle":
            lines = [line.strip() for line in content.decode("utf-8").splitlines() if line.strip()]
            line_one = next((line for line in lines if line.startswith("1 ")), None)
            line_two = next((line for line in lines if line.startswith("2 ")), None)
            if line_one is None or line_two is None:
                raise ValueError("The response did not contain a valid two-line element set.")
            content = f"ISS (ZARYA)\n{line_one}\n{line_two}\n".encode("utf-8")

        if not content:
            raise ValueError("The server returned an empty file.")

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        temporary_path.write_bytes(content)
        temporary_path.replace(destination)
        print(f"Downloaded {label}: {destination}")
        return True
    except (OSError, UnicodeError, URLError, ValueError) as error:
        temporary_path.unlink(missing_ok=True)
        print(f"Could not download {label}: {error}")
        return False


def main() -> int:
    """Download each required file and return a failing exit code on errors."""
    results = [download_file(*item) for item in DOWNLOADS]
    if all(results):
        print("All Sky Quest data files are ready.")
        return 0
    print("Some files are missing. Fix the error above and run this file again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
