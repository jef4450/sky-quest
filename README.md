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

4. Start the Ollama application before running Sky Quest. On Windows, open
   Ollama from the Start menu and leave it running. Alternatively, start its
   service in a separate PowerShell window:

   ```powershell
   ollama serve
   ```

5. While connected to the internet, download the astronomy data:

   ```powershell
   .\.venv\Scripts\python.exe download_data.py
   ```

   This saves `data/de421.bsp` and `data/iss.tle`. The `data/` folder is
   intentionally ignored by Git because the planetary file is large. The ISS
   orbit information changes and goes stale after a couple of weeks. Run the
   downloader again immediately before each outing while online so the ISS
   prediction uses current orbital data.

6. Set your private location in PowerShell environment variables; do not put
   your real coordinates in tracked source files. Replace the placeholders
   below locally:

   ```powershell
   $env:SKY_QUEST_LATITUDE = Read-Host "Latitude (decimal degrees)"
   $env:SKY_QUEST_LONGITUDE = Read-Host "Longitude (decimal degrees)"
   ```

   `config.py` uses placeholder `None` values when these are unset.
   Confirm `TIMEZONE`. Card modes select their matching narration persona:
   Lucy uses calm, Juvia quiet, and Natsu coach.

## Run Sky Quest

Create a printable card for tonight using your configured location:

```powershell
.\.venv\Scripts\python.exe main.py
```

Lucy is the default card. Choose another card with `--mode`; each run writes a
self-contained HTML file under `cards/`. Open that file in a browser and use
the browser's print command. The cards have their own print layout. In the
print dialog, turn off browser headers and footers so only the card is printed.

### Local web app

Start the mobile-friendly local interface from the project folder:

```powershell
.\.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:8765` in your browser. The app binds to loopback only,
uses the same offline astronomy data and card engines as the CLI, and does not
need an external web service. Choose **Stay in one place** for Juvia,
**Walk nearby** for Lucy, or **Run with stops** for Natsu; the car activity
is marked as coming soon. Juvia offers naked-eye or telescope output and
optional window direction/field-of-view settings. The result page previews
the card, provides a print button, and exposes its calculated facts in a
collapsible panel. Audio choices remain disabled until audio output exists.

The browser location button requires permission. Alternatively, copy decimal
latitude and longitude from a map. An optional checkbox saves the place
locally in `places.local.json`; it is ignored by Git and not printed on cards.
Run stops are entered separately with their own location and local time.
Status badges report Ollama/model availability, the local astronomy files,
and the age of saved ISS data (with a warning after ten days). Ollama is
optional: when it is unavailable, card generation uses the existing grounded
fallback text.
Lucy includes the five brightest catalog stars above the horizon, a computed
Polaris note, and fixed constellation guides when their anchor stars are up.
Juvia is a cozy window card; its hourly timeline includes planets, bright stars,
Polaris, eligible constellation guides, and telescope candidates. The candidate
catalog covers double stars, open and globular clusters, nebulae, and galaxies.
Candidates are listed only when the local calculation confirms astronomical
darkness, altitude above 15 degrees, and (for deep-sky objects) conservative
Moon conditions. This is not a guarantee of visibility: local light pollution,
weather, optics, and atmospheric conditions are not modeled. Natsu keeps the
pocket-sized walking route card.
The built-in star catalog covers both hemispheres and uses each card's own
location and observation time. Guides include the Big Dipper's pointers to
Polaris, Orion, the Summer Triangle, Cassiopeia, and the Southern Cross.

Juvia's window settings are optional values in `config.py`:

- `WINDOW_FACING = None` uses the full sky. Set it to a compass word such as
  `"north-east"` or a bearing from `0` through `360` degrees to point the
  window. Objects outside half the field of view are not in the window.
- `WINDOW_FIELD_OF_VIEW = 120.0` is the full angular width of the window view;
  it must be greater than 0 and no more than 360 degrees.
- `WINDOW_MIN_ALTITUDE = 10.0` is the minimum altitude for objects in a
  configured window; use a value from 0 through 90 degrees.

The minimum altitude is applied when `WINDOW_FACING` is set. Values are
validated when a card is generated.

```powershell
.\.venv\Scripts\python.exe main.py --mode lucy
.\.venv\Scripts\python.exe main.py --mode juvia
.\.venv\Scripts\python.exe main.py --mode natsu
```

Set an optional friendly place label without displaying coordinates:

```powershell
$env:SKY_QUEST_PLACE_LABEL = "My terrace"
```

For Natsu, create the ignored personal stop file from the example:

```powershell
Copy-Item .\stops.example.json .\stops.local.json
```

Replace the fictional stops with objects using `name`, `latitude`, `longitude`,
and a local `time` in `HH:MM` format. A planned time after midnight rolls to
the next date. Keep the personal file private; its
coordinates are used for calculations but never printed on the card. Every
stop shows its full local date and clock time, and the route header names the
configured timezone. If the local file is absent, the example route is used
and explicitly labeled as fictional placeholders; demo cards are always
labeled as demo placeholders.

Open the newest generated card in your browser, then press **Ctrl+P** to print:

```powershell
Start-Process (Get-ChildItem .\cards\*.html | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
```

Print a repeatable card for the fixed demo date October 15, 2026:

```powershell
.\.venv\Scripts\python.exe main.py --demo
.\.venv\Scripts\python.exe main.py --demo --mode juvia
.\.venv\Scripts\python.exe main.py --demo --mode natsu
```

Demo mode uses a fixed date and fictional sample locations, including
`stops.example.json` for Natsu. It still uses Skyfield and the downloaded data
files; it does not use fabricated astronomy. If Ollama is not running or the
model is missing, Sky Quest prints a clear message and uses a fact-only
template instead.

## Run tests

Run the test suite from the project folder:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Files

- `config.py` — private environment-based location, place label, timezone,
  local model, and writing persona.
- `download_data.py` — the only file that downloads data from the internet;
  run it once before going offline.
- `sky.py` — offline Moon, Jupiter, Saturn, twilight, sunset, and visible ISS
  calculations using files in `data/`.
- `stars.py` — offline Skyfield positions for the built-in bright-star catalog
  (including Polaris) and constellation-guide anchors.
- `deep_sky_targets.py` — a compact bundled J2000 catalog of double stars and
  deep-sky targets, with offline altitude, darkness, and conservative Moon
  screening for Juvia's telescope-candidate list.
- `verify_stars.py` — optional one-off Hipparcos coordinate and magnitude check;
  it downloads its catalog to the ignored `data/` folder and is not part of
  normal card generation.
- `constellation_guides.py` — fixed, non-generated star-hopping instructions
  shown only when their anchor stars are above the horizon.
- `scorer.py` — compares 15-minute slots during the first three hours of
  darkness and selects a best window with reasons.
- `narrate.py` — asks the local Ollama model for 2–3 sentences, then applies
  the grounding check and retries once if needed.
- `grounding_check.py` — flags unsupported celestial objects, directions,
  times, or numbers; failed generations are appended to `gemma_slips.log`.
- `html_cards.py` — renders self-contained, printable HTML for each card mode.
- `main.py` — combines the modules and writes the selected HTML card.
- `config.py` — also provides Juvia's optional window direction, field of view,
  and minimum object altitude.
- `stops.example.json` — fictional sample stops; copy it to the ignored
  `stops.local.json` for personal route stops.
- `requirements.txt` — Python dependencies.
- `docs/sample_gemma_slips.log` — cleaned sample narration diagnostics; actual
  `gemma_slips.log` is local and ignored by Git.

To run the optional Hipparcos catalog check while online:

```powershell
.\.venv\Scripts\python.exe verify_stars.py
```

The catalog is cached as `data/hip_main.dat`; `data/` is Git-ignored.

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
