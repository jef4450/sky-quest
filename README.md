# Sky Quest

Sky Quest is an offline night-sky planner. Skyfield calculates every sky fact
from the saved planetary ephemeris and ISS orbit file. Gemma only turns those
facts into friendly wording; it is not asked to calculate positions or times.

After the one-time data download, sky calculations do not access the internet.
Narration is sent only to the Ollama service running on your own computer.

## Setup

1. Install Python 3.10 or newer and [Ollama](https://ollama.com/).
2. In this project folder, create and activate a virtual environment:

   ```powershell
   C:\python312\python.exe -m venv .venv
   ```

3. Install the Python packages and download the local model:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ollama pull gemma3:1b
   ```

4. While connected to the internet, download the astronomy data once:

   ```powershell
   .\.venv\Scripts\python.exe download_data.py
   ```

   This saves `data/de421.bsp` and `data/iss.tle`. The `data/` folder is
   intentionally ignored by Git because the planetary file is large. The ISS
   orbit information changes, so rerun the downloader occasionally while
   online to refresh it.

5. Edit `config.py`: set `LATITUDE` and `LONGITUDE` to decimal coordinates,
   choose a `PERSONA` (`calm`, `coach`, `precise`, or `quiet`), and confirm
   `TIMEZONE`. `--demo` uses sample Bengaluru coordinates without changing
   your config.

## Run Sky Quest

Print tonight's card using your configured location:

```powershell
.\.venv\Scripts\python.exe main.py
```

Print a repeatable card for the fixed date October 15, 2026:

```powershell
.\.venv\Scripts\python.exe main.py --demo
```

The demo date still uses real Skyfield calculations and needs the downloaded
data files. It does not use fabricated astronomy. If Ollama is not running or
the model is missing, Sky Quest prints a clear message and uses a fact-only
template instead.

## Files

- `config.py` — location, timezone, local model, and writing persona.
- `download_data.py` — the only file that downloads data from the internet;
  run it once before going offline.
- `sky.py` — offline Moon, Jupiter, Saturn, twilight, sunset, and visible ISS
  calculations using files in `data/`.
- `scorer.py` — compares 15-minute slots during the first three hours of
  darkness and selects a best window with reasons.
- `narrate.py` — asks the local Ollama model for 2–3 sentences, then applies
  the grounding check and retries once if needed.
- `grounding_check.py` — flags unsupported celestial objects, directions,
  times, or numbers; failed generations are appended to `gemma_slips.log`.
- `main.py` — combines the modules and prints the plain-text card.
- `requirements.txt` — Python dependencies.

`config.py`, `sky.py`, `scorer.py`, `narrate.py`, and `grounding_check.py` are
modules imported by `main.py`; `download_data.py` and `main.py` are the scripts
you run directly.

## Compare the sky facts with an app

Use an observing app such as Stellarium or Sky Guide. Set the app's location
to the same latitude and longitude as `config.py`, set its date and time to
the displayed best-window time, and compare the Moon and Jupiter altitude and
compass direction. The card reports altitude in degrees and direction from
north. Confirm that the app is showing the same local time and location before
comparing; small differences in time, atmospheric refraction settings, or
coordinates can shift the displayed position.
