"""Local-only web interface for Sky Quest."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
from pathlib import Path
import re
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import config
import main as card_engine
from sky import ISS_FILE, PLANET_FILE


HOST = "127.0.0.1"
PORT = 8765
PROJECT_DIR = Path(__file__).resolve().parent
PLACES_FILE = PROJECT_DIR / "places.local.json"
MAX_REQUEST_BYTES = 64 * 1024
ACTIVITIES = {
    "stay": ("Stay in one place", "juvia"),
    "walk": ("Walk nearby", "lucy"),
    "run": ("Run with stops", "natsu"),
    "car": ("Ride in a car", None),
}
COMPASS_POINTS = {
    "north", "north-east", "east", "south-east",
    "south", "south-west", "west", "north-west",
}
COORDINATE_PAIR = re.compile(
    r"(?<!\w)[+-]?\d{1,3}\.\d+\s*[,/]\s*[+-]?\d{1,3}\.\d+(?!\w)"
)

STYLE = """
:root { color-scheme: light; font-family: Arial, sans-serif; color: #101820; background: #f2f6f8; }
* { box-sizing: border-box; }
body { margin: 0; font-size: 18px; line-height: 1.5; }
header, main { width: min(100% - 28px, 980px); margin: auto; }
header { padding: 22px 0 10px; }
h1 { margin: 0; font-size: clamp(2rem, 6vw, 3.25rem); line-height: 1.08; }
h2 { font-size: 1.45rem; margin: 1.3em 0 .45em; }
p { margin: .5em 0 1em; }
.status { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
.badge { padding: 7px 11px; background: #fff; border: 2px solid #234; border-radius: 8px; font-size: .88rem; font-weight: 700; }
.warning { border-color: #a43b00; color: #762800; }
.panel, .activity, fieldset { background: #fff; border: 2px solid #263b4a; border-radius: 12px; padding: 18px; margin: 14px 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 12px; }
.activity { display: block; color: inherit; text-decoration: none; min-height: 120px; }
.activity:hover, .activity:focus { outline: 4px solid #146c94; }
label { display: block; font-weight: 700; margin: 12px 0 4px; }
input, select, button { font: inherit; }
input, select { width: 100%; min-height: 48px; padding: 8px 10px; border: 2px solid #384e5b; border-radius: 7px; background: #fff; color: #111; }
input[type=checkbox] { width: 24px; height: 24px; vertical-align: middle; }
.help { color: #243744; font-size: .9rem; }
button, .button { display: inline-block; border: 0; border-radius: 8px; padding: 12px 18px; background: #064f70; color: #fff; font-weight: 700; cursor: pointer; text-decoration: none; margin: 8px 5px 8px 0; }
button.secondary { background: #31434f; }
.error { border-left: 6px solid #a52713; padding: 10px 14px; background: #fff1ec; font-weight: 700; }
.stop { border: 1px solid #8b9ba4; border-radius: 8px; padding: 12px; margin: 12px 0; }
.preview { width: 100%; height: min(78vh, 1000px); background: white; border: 2px solid #263b4a; border-radius: 8px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #fff; padding: 14px; border: 1px solid #81909a; border-radius: 8px; }
details { margin: 18px 0; }
.muted { color: #33454f; }
@media (max-width: 600px) { body { font-size: 17px; } .panel, fieldset { padding: 14px; } }
"""


def _status_snapshot() -> dict:
    """Inspect only local services and saved files; never contact the network."""
    ollama_reachable = False
    model_available = False
    try:
        request = Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urlopen(request, timeout=0.7) as response:
            payload = json.loads(response.read().decode("utf-8"))
        ollama_reachable = True
        models = payload.get("models", []) if isinstance(payload, dict) else []
        model_available = isinstance(models, list) and any(
            item.get("name") == config.MODEL_NAME
            or item.get("model") == config.MODEL_NAME
            for item in models
            if isinstance(item, dict)
        )
    except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        pass

    iss_age_days = None
    try:
        lines = ISS_FILE.read_text(encoding="utf-8").splitlines()
        tle_line = next(line for line in lines if line.startswith("1 "))
        epoch = tle_line[18:32]
        year = int(epoch[:2])
        year += 2000 if year < 57 else 1900
        day_of_year = float(epoch[2:])
        epoch_time = datetime(year, 1, 1, tzinfo=ZoneInfo("UTC"))
        epoch_time += timedelta(days=day_of_year - 1)
        iss_age_days = max(
            0, int((datetime.now(ZoneInfo("UTC")) - epoch_time).total_seconds() // 86400)
        )
    except (OSError, StopIteration, ValueError, IndexError):
        pass

    return {
        "ollama_reachable": ollama_reachable,
        "model_available": model_available,
        "planet_data": PLANET_FILE.is_file(),
        "iss_data": ISS_FILE.is_file(),
        "iss_age_days": iss_age_days,
    }


def _status_bar() -> str:
    status = _status_snapshot()
    items = [
        ("Ollama reachable" if status["ollama_reachable"] else "Ollama not reachable",
         status["ollama_reachable"]),
        (
            "Model ready"
            if status["model_available"]
            else (
                "Model not pulled"
                if status["ollama_reachable"]
                else "Model status unavailable"
            ),
            status["model_available"],
        ),
        ("Planet data ready" if status["planet_data"] else "Planet data missing",
         status["planet_data"]),
        ("ISS data ready" if status["iss_data"] else "ISS data missing",
         status["iss_data"]),
    ]
    if status["iss_age_days"] is not None:
        days = status["iss_age_days"]
        items.append((f"ISS data: {days} day(s) old", days <= 10))
    else:
        items.append(("ISS data age unavailable", False))
    return '<section class="status" aria-label="Local system status">' + "".join(
        f'<span class="badge{" warning" if not healthy else ""}">{escape(label)}</span>'
        for label, healthy in items
    ) + "</section>"


def _read_places() -> list[dict]:
    try:
        data = json.loads(PLACES_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [
        place for place in data
        if isinstance(place, dict)
        and isinstance(place.get("name"), str)
        and isinstance(place.get("latitude"), (int, float))
        and isinstance(place.get("longitude"), (int, float))
    ]


def _shell(title: str, content: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{STYLE}</style></head><body>"
        f"<header><h1>Sky Quest</h1>{_status_bar()}</header>"
        f"<main>{content}</main></body></html>"
    )


def _activity_page() -> str:
    cards = []
    descriptions = {
        "stay": "A window or open-sky plan with equipment and window options.",
        "walk": "A relaxed local sky card for a stationary viewing place.",
        "run": "A route card that calculates each stop independently.",
        "car": "Coming when Grey's mode exists.",
    }
    for key, (label, _) in ACTIVITIES.items():
        cards.append(
            f'<a class="activity" href="/?activity={key}"><h2>{escape(label)}</h2>'
            f"<p>{escape(descriptions[key])}</p></a>"
        )
    return _shell(
        "Choose an activity",
        "<p>Choose how you will be outside. Sky facts are calculated locally.</p>"
        f'<div class="grid">{"".join(cards)}</div>',
    )


def _stop_fields(index: int) -> str:
    return (
        f'<fieldset class="stop"><legend>Stop {index}</legend>'
        '<label>Stop name<input name="stop_name" maxlength="80" required></label>'
        '<label>Latitude<input name="stop_latitude" type="number" min="-90" max="90" step="any" required></label>'
        '<label>Longitude<input name="stop_longitude" type="number" min="-180" max="180" step="any" required></label>'
        '<label>Local stop time<input name="stop_time" type="time" required></label>'
        '<button type="button" class="secondary remove-stop">Remove stop</button></fieldset>'
    )


def _form_page(activity: str, error: str = "") -> str:
    label, mode = ACTIVITIES[activity]
    if mode is None:
        return _shell(
            label,
            '<section class="panel"><h2>Coming soon</h2><p>Ride in a car is coming when Grey&#x27;s mode exists. The depth choice will be available when that card mode is ready.</p>'
            '<a class="button" href="/">Choose another activity</a></section>',
        )

    places = _read_places()
    now = datetime.now(ZoneInfo(config.TIMEZONE))
    default_date = now.strftime("%Y-%m-%d")
    default_time = now.strftime("%H:%M")
    place_options = ['<option value="">Enter a new place</option>']
    for place in places:
        place_options.append(
            f'<option value="{escape(place["name"], quote=True)}">'
            f'{escape(place["name"])}</option>'
        )

    activity_controls = ""
    if activity in {"walk", "stay"}:
        activity_controls = (
            '<fieldset><legend>Card detail</legend>'
            '<label>How deep do you want to go?<select name="depth">'
            f'<option value="casual"{" selected" if config.DEPTH == "casual" else ""}>Casual night sky view</option>'
            f'<option value="explorer"{" selected" if config.DEPTH == "explorer" else ""}>Explorer</option>'
            f'<option value="deep"{" selected" if config.DEPTH == "deep" else ""}>Deep dive</option>'
            '</select></label></fieldset>'
        )
    if activity == "stay":
        activity_controls += (
            '<fieldset><legend>Viewing setup</legend>'
            '<label>Equipment<select name="equipment"><option value="naked_eye">Naked eye</option>'
            '<option value="telescope">Telescope</option></select></label>'
            '<label>Window facing (optional)<input name="window_facing" placeholder="e.g. north-east or 90"></label>'
            '<label>Window field of view in degrees<input name="field_of_view" type="number" min="0.1" max="360" step="any" value="120"></label>'
            '<p class="help">Leave the facing blank to use the full sky.</p></fieldset>'
        )
    if activity == "run":
        activity_controls = (
            '<fieldset><legend>Route stops</legend>'
            '<p class="help">Each stop uses its own coordinates and local time.</p>'
            f'<div id="stops">{_stop_fields(1)}</div>'
            '<button type="button" id="add-stop" class="secondary">Add stop</button>'
            '<button type="button" id="copy-coordinates" class="secondary">Copy place coordinates to blank stops</button>'
            '</fieldset>'
        )

    error_html = f'<p class="error">{escape(error)}</p>' if error else ""
    script = ""
    if activity == "run":
        script = """<script>
const container = document.getElementById('stops');
function bindRemove(button) { button.addEventListener('click', () => {
  if (container.querySelectorAll('.stop').length > 1) button.closest('.stop').remove();
}); }
container.querySelectorAll('.remove-stop').forEach(bindRemove);
document.getElementById('add-stop').addEventListener('click', () => {
  if (container.querySelectorAll('.stop').length >= 12) return;
  const copy = container.querySelector('.stop').cloneNode(true);
  copy.querySelectorAll('input').forEach(input => input.value = '');
  copy.querySelector('legend').textContent = `Stop ${container.querySelectorAll('.stop').length + 1}`;
  bindRemove(copy.querySelector('.remove-stop')); container.appendChild(copy);
});
document.getElementById('copy-coordinates').addEventListener('click', () => {
  const lat = document.querySelector('[name="latitude"]').value;
  const lon = document.querySelector('[name="longitude"]').value;
  container.querySelectorAll('.stop').forEach(stop => {
    const fields = stop.querySelectorAll('input');
    if (!fields[1].value) fields[1].value = lat;
    if (!fields[2].value) fields[2].value = lon;
  });
});
</script>"""

    content = (
        f'<a href="/">← Activities</a><section class="panel"><h2>{escape(label)}</h2>'
        f"<p>Enter a place and a local date/time. Coordinates are used only for calculations.</p>"
        f"{error_html}<form method=\"post\" action=\"/generate\">"
        f'<input type="hidden" name="activity" value="{activity}">'
        f'<label>Saved place<select id="saved-place"><option value="">Choose a saved place</option>'
        f'{"".join(place_options)}</select></label>'
        '<label>Place label<input name="place_label" maxlength="80" placeholder="e.g. Home"></label>'
        '<label>Latitude<input name="latitude" type="number" min="-90" max="90" step="any" required></label>'
        '<label>Longitude<input name="longitude" type="number" min="-180" max="180" step="any" required></label>'
        '<p class="help">Copy decimal coordinates from your map app. Or use the location button with browser permission.</p>'
        '<button type="button" id="geolocate" class="secondary">Use my location</button>'
        '<label><input type="checkbox" name="save_place" value="yes"> Save this place on this computer</label>'
        f'<label>Date<input name="date" type="date" value="{default_date}" required></label>'
        f'<label>Start time<input name="start_time" type="time" value="{default_time}" required></label>'
        f"{activity_controls}"
        '<fieldset><legend>Output</legend><label>Output format<select name="output">'
        '<option value="card">Printable card</option><option value="audio" disabled>Audio (not available yet)</option>'
        '<option value="both" disabled>Card and audio (not available yet)</option></select></label></fieldset>'
        '<button type="submit">Build my card</button></form></section>'
        """<script>
document.getElementById('geolocate').addEventListener('click', () => {
  if (!navigator.geolocation) { alert('Location is not available in this browser.'); return; }
  navigator.geolocation.getCurrentPosition(position => {
    document.querySelector('[name="latitude"]').value = position.coords.latitude;
    document.querySelector('[name="longitude"]').value = position.coords.longitude;
  }, () => alert('Could not get your location. You can enter map coordinates instead.'));
});
const saved = document.getElementById('saved-place');
saved.addEventListener('change', () => {
  const option = saved.selectedOptions[0];
  if (!option || !option.value) return;
  fetch(`/place?name=${encodeURIComponent(option.value)}`).then(response => response.json()).then(place => {
    if (!place.latitude && place.latitude !== 0) return;
    document.querySelector('[name="latitude"]').value = place.latitude;
    document.querySelector('[name="longitude"]').value = place.longitude;
  });
  document.querySelector('[name="place_label"]').value = option.value;
});
</script>"""
        + script
    )
    return _shell(label, content)


def _field(form: dict[str, list[str]], key: str, default: str = "") -> str:
    values = form.get(key, [])
    return values[0].strip() if values else default


def _number(value: str, label: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"Enter a valid {label}.") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{label.capitalize()} must be between {minimum:g} and {maximum:g}.")
    return number


def _parse_common(form: dict[str, list[str]]) -> tuple[str, float, float, datetime]:
    activity = _field(form, "activity")
    if activity not in ACTIVITIES or ACTIVITIES[activity][1] is None:
        raise ValueError("Choose one of the available activities.")
    latitude = _number(_field(form, "latitude"), "latitude", -90, 90)
    longitude = _number(_field(form, "longitude"), "longitude", -180, 180)
    try:
        day = datetime.strptime(_field(form, "date"), "%Y-%m-%d").date()
        clock = datetime.strptime(_field(form, "start_time"), "%H:%M").time()
    except ValueError as error:
        raise ValueError("Enter a valid date and time.") from error
    when = datetime.combine(day, time(clock.hour, clock.minute), tzinfo=ZoneInfo(config.TIMEZONE))
    return activity, latitude, longitude, when


def _parse_stops(form: dict[str, list[str]]) -> list[dict]:
    names = form.get("stop_name", [])
    latitudes = form.get("stop_latitude", [])
    longitudes = form.get("stop_longitude", [])
    times = form.get("stop_time", [])
    if not names or len(names) > 12 or not (len(names) == len(latitudes) == len(longitudes) == len(times)):
        raise ValueError("Add between 1 and 12 complete route stops.")
    stops = []
    for name, latitude, longitude, clock in zip(names, latitudes, longitudes, times):
        name = name.strip()
        if not name or len(name) > 80:
            raise ValueError("Each stop needs a name of 1 to 80 characters.")
        try:
            parsed_time = datetime.strptime(clock, "%H:%M")
        except ValueError as error:
            raise ValueError("Each stop needs a valid local time.") from error
        stops.append({
            "name": name,
            "latitude": _number(latitude, "stop latitude", -90, 90),
            "longitude": _number(longitude, "stop longitude", -180, 180),
            "time": parsed_time.strftime("%H:%M"),
        })
    return stops


def _window_settings(form: dict[str, list[str]]) -> dict:
    facing_text = _field(form, "window_facing").lower()
    facing: str | float | None
    if not facing_text:
        facing = None
    elif facing_text in COMPASS_POINTS:
        facing = facing_text
    else:
        facing = _number(facing_text, "window facing bearing", 0, 360)
    fov = _number(_field(form, "field_of_view", "120"), "field of view", 0, 360)
    if fov <= 0:
        raise ValueError("Field of view must be greater than 0 and at most 360.")
    return {
        "facing": facing,
        "field_of_view": fov,
        "minimum_altitude": config.WINDOW_MIN_ALTITUDE,
    }


def _depth_setting(form: dict[str, list[str]], activity: str) -> str:
    if activity == "run":
        return config.DEPTH
    depth = _field(form, "depth", config.DEPTH)
    if depth not in card_engine.DEPTH_LIMITS:
        raise ValueError("Invalid depth; choose casual, explorer, or deep card detail.")
    return depth


def _save_place(name: str, latitude: float, longitude: float) -> None:
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError("A saved place needs a name of 1 to 80 characters.")
    places = [place for place in _read_places() if place["name"] != name]
    places.append({"name": name, "latitude": latitude, "longitude": longitude})
    PLACES_FILE.write_text(json.dumps(places, indent=2) + "\n", encoding="utf-8")


def _hide_input_coordinates(text: str, coordinates: tuple[float, float]) -> str:
    def redact(match):
        try:
            number = float(match.group(0))
        except ValueError:
            return match.group(0)
        return (
            "[location omitted]"
            if number in coordinates
            else match.group(0)
        )

    return re.sub(
        r"(?<![A-Za-z0-9.])[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?![A-Za-z0-9.])",
        redact,
        text,
    )


def _safe_facts(value):
    """Remove coordinate fields and redact coordinate-like values from facts."""
    if isinstance(value, dict):
        return {
            key: _safe_facts(item)
            for key, item in value.items()
            if key.casefold() not in {"latitude", "longitude", "lat", "lon", "coordinates"}
        }
    if isinstance(value, list):
        return [_safe_facts(item) for item in value]
    if isinstance(value, str):
        return COORDINATE_PAIR.sub("[location omitted]", value)
    return value


def _result_page(card_html: str, facts: dict) -> str:
    safe_card = escape(card_html, quote=True)
    facts_json = escape(
        json.dumps(_safe_facts(facts), ensure_ascii=False, indent=2),
        quote=False,
    )
    content = (
        '<a href="/">← Activities</a><section class="panel"><h2>Your sky card</h2>'
        '<button type="button" id="print-card">Print card</button>'
        f'<iframe class="preview" title="Printable card preview" srcdoc="{safe_card}"></iframe>'
        '<details><summary>Facts this card is based on</summary>'
        f"<pre>{facts_json}</pre></details></section>"
        """<script>
document.getElementById('print-card').addEventListener('click', () => {
  document.querySelector('.preview').contentWindow.print();
});
</script>"""
    )
    return _shell("Your Sky Quest card", content)


def _handle_generate(form: dict[str, list[str]]) -> str:
    activity, latitude, longitude, when = _parse_common(form)
    mode = ACTIVITIES[activity][1]
    output = _field(form, "output", "card")
    if output != "card":
        raise ValueError("Audio output is not available yet; choose Printable card.")

    stops = None
    window = None
    equipment = "telescope"
    depth = _depth_setting(form, activity)
    if activity == "run":
        stops = _parse_stops(form)
    elif activity == "stay":
        equipment = _field(form, "equipment", "naked_eye")
        if equipment not in {"naked_eye", "telescope"}:
            raise ValueError("Choose naked eye or telescope.")
        window = _window_settings(form)

    place_label = _field(form, "place_label", "My observing place")[:80]
    place_label = _hide_input_coordinates(place_label, (latitude, longitude))
    if stops is not None:
        for stop in stops:
            stop["name"] = _hide_input_coordinates(
                stop["name"], (stop["latitude"], stop["longitude"])
            )
    if _field(form, "save_place") == "yes":
        _save_place(place_label, latitude, longitude)

    context = {}
    card_engine.print_card(
        latitude,
        longitude,
        when,
        mode=mode,
        stops_override=stops,
        window_settings=window,
        equipment=equipment,
        result_data=context,
        place_label=place_label or "My observing place",
        depth=depth,
    )
    return _result_page(context["html"], context["facts"])


class SkyQuestHandler(BaseHTTPRequestHandler):
    server_version = "SkyQuestLocal/1.0"

    def log_message(self, format, *args):
        # Standard HTTP access logs may echo private form values or query strings.
        return

    def _send(self, status: int, document: str) -> None:
        body = document.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _is_local_request(self) -> bool:
        try:
            is_loopback = ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            return False
        host_header = self.headers.get("Host", "")
        hostname = urlparse(f"//{host_header}").hostname
        return is_loopback and hostname in {"127.0.0.1", "localhost"}

    def do_GET(self) -> None:
        if not self._is_local_request():
            self._send(403, _shell("Local only", "<p>This app accepts local connections only.</p>"))
            return
        query = parse_qs(urlparse(self.path).query)
        if urlparse(self.path).path == "/place":
            name = query.get("name", [""])[0]
            place = next(
                (item for item in _read_places() if item["name"] == name),
                None,
            )
            if place is None:
                self._send_json(404, {"error": "Saved place not found."})
            else:
                self._send_json(200, {
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                })
            return
        activity = query.get("activity", [""])[0]
        if not activity:
            self._send(200, _activity_page())
        elif activity in ACTIVITIES:
            self._send(200, _form_page(activity))
        else:
            self._send(404, _shell("Not found", '<p>Choose an activity from <a href="/">the home page</a>.</p>'))

    def do_POST(self) -> None:
        if not self._is_local_request() or urlparse(self.path).path != "/generate":
            self._send(403, _shell("Local only", "<p>This request is unavailable.</p>"))
            return
        activity = ""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("The submitted form is too large.")
            body = self.rfile.read(length).decode("utf-8")
            form = parse_qs(body, keep_blank_values=True)
            activity = _field(form, "activity")
            if activity not in ACTIVITIES:
                raise ValueError("Choose a valid activity.")
            self._send(200, _handle_generate(form))
        except (ValueError, OSError, FileNotFoundError) as error:
            safe_error = str(error)
            self._send(400, _form_page(
                activity if activity in ACTIVITIES else "stay",
                safe_error,
            ))


def serve(host: str = HOST, port: int = PORT) -> None:
    """Run the web app on loopback only."""
    if host != "127.0.0.1":
        raise ValueError("Sky Quest web app must bind to 127.0.0.1.")
    server = ThreadingHTTPServer((HOST, port), SkyQuestHandler)
    print(f"Sky Quest web app: http://{HOST}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSky Quest web app stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
