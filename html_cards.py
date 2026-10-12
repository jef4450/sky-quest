"""Render self-contained, printable Sky Quest cards."""

from __future__ import annotations

from html import escape
import re


NO_ISS_MESSAGE = "No visible ISS pass tonight."
_COORDINATE_PAIR = re.compile(
    r"(?<!\w)[+-]?\d{1,3}\.\d+\s*[,/]\s*[+-]?\d{1,3}\.\d+(?!\w)"
)

_BASE_STYLE = """
@page { size: A4; margin: 15mm; }
* { box-sizing: border-box; }
body { margin: 0; color: #111; background: #fff; font: 15.5pt/1.35 Arial, sans-serif; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
.card { width: 180mm; margin: 0; break-inside: avoid; page-break-inside: avoid; }
h1 { margin: 0 0 3mm; font-size: 25pt; line-height: 1.1; break-after: avoid; page-break-after: avoid; }
h2 { margin: 5mm 0 2mm; font-size: 24pt; line-height: 1.15; break-after: avoid; page-break-after: avoid; }
p { margin: 2mm 0; }
.meta { font-size: 14pt; }
.window { margin: 4mm 0; padding: 4mm; border: 1.5pt solid #111; font-weight: 700; break-inside: avoid; page-break-inside: avoid; }
.window-label { display: block; font-size: 20pt; }
.window-time { display: block; margin-top: 1mm; font-size: 36pt; line-height: 1.1; }
.list { margin: 2mm 0 0; padding: 0; list-style: none; }
.item { display: grid; grid-template-columns: 14mm 1fr; gap: 4mm; align-items: center; margin: 0; padding: 4mm 2mm; border-bottom: 1pt solid #111; line-height: 1.3; break-inside: avoid; page-break-inside: avoid; }
.box { display: block; width: 12mm; height: 12mm; border: 1.5pt solid #111; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
.iss { margin-top: 4mm; padding: 3mm; border: 1.5pt solid #111; font-weight: 700; break-inside: avoid; page-break-inside: avoid; }
.small { font-size: 14pt; }
.lucy .intro { margin: 3mm 0; font-size: 15pt; }
.juvia { font-size: 14pt; }
.juvia .intro { font-size: 13.5pt; }

.juvia { width: 180mm; font-size: 13.5pt; }
.juvia h1 { font-size: 22pt; }
.juvia h2 { margin: 2mm 0 1mm; font-size: 17pt; }
.juvia .facing { margin: 1mm 0 2mm; font-size: 13pt; font-weight: 700; }
.juvia .timeline { margin: 0; padding: 0; list-style: none; }
.juvia .timeline-row { display: grid; grid-template-columns: 23mm 1fr; gap: 2mm; padding: 1mm 0; border-top: 1pt solid #111; break-inside: avoid; page-break-inside: avoid; }
.juvia .timeline-time { font-size: 16pt; font-weight: 700; }
.juvia .timeline-items { margin: 0; padding: 0; list-style: none; }
.juvia .timeline-item { display: inline-flex; align-items: center; gap: 1mm; margin: 0 2mm 1mm 0; font-size: 11.5pt; break-inside: avoid; page-break-inside: avoid; }
.juvia .timeline-item.no-checkbox { display: inline; }
.juvia .timeline-item .box { width: 4mm; height: 4mm; flex: none; }
.juvia .row-empty { font-weight: 700; }
.juvia .row-iss { margin-top: 1mm; font-weight: 700; }
.juvia .telescope-candidate { display: block; margin-top: 1mm; font-size: 10.5pt; break-inside: avoid; page-break-inside: avoid; }
.notes { height: 30mm; margin-top: 1mm; border: 1pt solid #111; break-inside: avoid; page-break-inside: avoid; }
.juvia .naked-eye-notes { margin: 0 0 1mm; font-size: 11pt; }
.juvia .iss { margin-top: 1mm; padding: 1.5mm; font-size: 11pt; }
.natsu { width: 105mm; font-size: 14pt; }
.natsu h1 { font-size: 20pt; }
.natsu h2 { margin: 3mm 0 1mm; font-size: 17pt; }
.natsu .window { margin: 3mm 0; padding: 3mm; }
.natsu .window-label { font-size: 15pt; }
.natsu .window-time { font-size: 24pt; }
.natsu .item { grid-template-columns: 14mm 1fr; gap: 3mm; padding: 3mm 1mm; }
.natsu .box { width: 11mm; height: 11mm; }
.natsu .route-span { display: block; margin: 3mm 0; padding: 2mm 0; border-bottom: 1pt solid #111; font-size: 17pt; font-weight: 700; }
.natsu .intro { margin-top: 2mm; font-size: 13pt; }
.natsu .stop-row { display: grid; }
.natsu .stop-row.no-target { display: block; }
.natsu .stop-name { display: block; margin-bottom: 1mm; font-weight: 700; }
.natsu .stop-detail { display: block; }
.natsu .stop-status { font-weight: 700; }
.natsu .stop-source { margin: 2mm 0; font-size: 12pt; font-weight: 700; }
.natsu .iss { margin-top: 3mm; padding: 2mm; font-size: 12pt; }
.safety { margin-top: 4mm; font-size: 17pt; font-weight: 700; break-inside: avoid; page-break-inside: avoid; }
.lucy { font-size: 15pt; }
.lucy h2 { margin: 2mm 0 1mm; font-size: 22pt; }
.lucy .window { margin: 2mm 0; padding: 3mm; }
.lucy .window-label { font-size: 18pt; }
.lucy .window-time { font-size: 32pt; }
.lucy .intro { margin: 2mm 0; font-size: 15pt; }
.lucy-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; }
.lucy .item { grid-template-columns: 8mm 1fr; gap: 2mm; padding: 1.5mm 1mm; font-size: 13.5pt; }
.lucy .item.no-checkbox { grid-template-columns: 1fr; }
.lucy .box { width: 7mm; height: 7mm; }
.lucy .guide-list { margin: 0; padding-left: 5mm; }
.lucy .guide-item { margin: 1mm 0; font-size: 15pt; line-height: 1.25; break-inside: avoid; }
.lucy .polaris { margin: 2mm 0; }
.lucy .small { margin-top: 2mm; }
.lucy .iss { margin-top: 2mm; padding: 2mm; }
"""


def _e(value: object) -> str:
    safe_text = _COORDINATE_PAIR.sub("[location omitted]", str(value))
    return escape(safe_text, quote=True)


def _checklist_item(item: dict | str) -> str:
    if isinstance(item, str):
        text = item
        checkable = True
    else:
        text = item["text"]
        checkable = item.get("checkable", item.get("visible", False))
    checkbox = (
        '<span class="box" aria-label="unchecked"></span>'
        if checkable
        else ""
    )
    no_checkbox = "" if checkable else " no-checkbox"
    return (
        f'<li class="item{no_checkbox}">{checkbox}'
        f'<span>{_e(text)}</span></li>'
    )


def _iss_section(iss_passes: list[dict]) -> str:
    if not iss_passes:
        content = NO_ISS_MESSAGE
    else:
        content = "Visible ISS pass (local time): " + "; ".join(
            f"{item.get('local_date_time', item['start'])}, from {item['appears_from']} "
            f"toward {item['disappears_toward']}"
            for item in iss_passes
        )
    return f'<p class="iss">{_e(content)}</p>'


def _header(data: dict, mode: str) -> str:
    header = (
        f'<header><h1>Sky Quest - {_e(data["title"])}</h1>'
        f'<p class="meta">{_e(data["date"])} - {_e(data["place_label"])}</p>'
    )
    if mode == "natsu":
        return (
            header
            + f'<p class="route-span">{_e(data["route_text"])}</p></header>'
        )
    if mode == "juvia":
        facing = data.get("window_facing")
        facing_line = (
            f'<p class="facing">Window facing: {_e(facing)}</p>'
            if facing
            else ""
        )
        return header + facing_line + "</header>"
    return (
        header
        + f'<p class="window"><span class="window-label">Best viewing window:</span>'
        + f'<strong class="window-time">{_e(data["window_text"])}</strong></p></header>'
    )


def _natsu_stop(stop: dict) -> str:
    date_prefix = f'{_e(stop["date"])}, ' if stop.get("date") else ""
    if stop["target"]:
        target = stop["target"]
        checkbox = '<span class="box" aria-label="unchecked"></span>'
        detail = (
            f'{date_prefix}{_e(stop["time"])} local: look '
            f'{_e(target["direction"])}, {_e(target["object"])} '
            f'{_e(target["height"])}'
        )
    else:
        checkbox = ""
        detail = (
            f'{date_prefix}{_e(stop["time"])} local: '
            f'<span class="stop-status">{_e(stop["status"])}</span>'
        )
    return (
        f'<li class="item stop-row{" no-target" if not stop["target"] else ""}">{checkbox}<span>'
        f'<strong class="stop-name">Stop {_e(stop["number"])} - {_e(stop["name"])}</strong>'
        f'<span class="stop-detail">{detail}</span></span></li>'
    )


def render_html_card(mode: str, data: dict) -> str:
    """Return complete HTML for one supported card mode."""
    if mode not in {"lucy", "juvia", "natsu"}:
        raise ValueError("mode must be lucy, juvia, or natsu")

    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Sky Quest - {_e(data['title'])}</title>",
        f"<style>{_BASE_STYLE}</style></head>",
        f'<body><main class="card {mode}">',
        _header(data, mode),
    ]

    if mode == "lucy":
        parts.append(f'<p class="intro">{_e(data["intro"])}</p>')
        parts.append('<div class="lucy-columns">')
        parts.append("<section><h2>Tonight's checklist</h2><ul class=\"list\">")
        for item in data["checklist"]:
            parts.append(_checklist_item(item))
        if data.get("polaris"):
            parts.append(_checklist_item(data["polaris"]))
        parts.append("</ul></section><section><h2>Bright stars</h2><ul class=\"list\">")
        for star in data.get("stars", []):
            parts.append(
                _checklist_item({
                    "text": f'{star["name"]}: {star["direction"]}, {star["height"]}',
                    "visible": star["above_horizon"],
                })
            )
        if not data.get("stars"):
            parts.append('<li class="item no-checkbox"><span>No catalog stars are above the horizon.</span></li>')
        parts.append("</ul></section></div>")
        guides = data.get("guides", [])
        if guides:
            parts.append("<h2>Constellation guides</h2><ul class=\"guide-list\">")
            for guide in guides:
                parts.append(f'<li class="guide-item">{_e(guide["text"])}</li>')
            parts.append("</ul>")
        parts.append('<p class="small">Give your eyes 10 minutes to adjust.</p>')
    elif mode == "juvia":
        parts.append(f'<p class="intro">{_e(data["intro"])}</p>')
        parts.append("<h2>Estimated viewing times</h2>")
        parts.append('<ul class="timeline">')
        for row in data["timeline"]:
            parts.append(
                '<li class="timeline-row">'
                f'<strong class="timeline-time">{_e(row["time"])}</strong>'
                '<div class="timeline-content"><ul class="timeline-items">'
            )
            for item in row["items"]:
                checkable = item["checkable"]
                checkbox = (
                    '<span class="box" aria-label="unchecked"></span>'
                    if checkable
                    else ""
                )
                no_checkbox = "" if checkable else " no-checkbox"
                parts.append(
                    f'<li class="timeline-item{no_checkbox}">{checkbox}'
                    f'<span>{_e(item["text"])}'
                    + (
                        f'<span class="item-note">{_e(item["note"])}</span>'
                        if item.get("note")
                        else ""
                    )
                    + "</span></li>"
                )
            if row["empty"]:
                parts.append(
                    '<li class="row-empty">nothing in your window at this time</li>'
                )
            for iss_pass in row["iss_passes"]:
                parts.append(
                    '<li class="row-iss">ISS (local time): '
                    f'{_e(iss_pass.get("local_date_time", iss_pass["start"]))}; from '
                    f'{_e(iss_pass["appears_from"])} toward '
                    f'{_e(iss_pass["disappears_toward"])}</li>'
                )
            for target in row.get("telescope_targets", []):
                parts.append(
                    '<li class="telescope-candidate">'
                    f'{_e(target["catalog"])} ({_e(target["name"])}), '
                    f'{_e(target["kind"])}: {_e(target["direction"])}, '
                    f'{_e(target["height"])}, altitude '
                    f'{_e(target["altitude_degrees"])} degrees</li>'
                )
            parts.append("</ul></div></li>")
        if not data["timeline"]:
            parts.append(
                '<li class="timeline-row">No dark timeline is available.</li>'
            )
        if data.get("equipment", "telescope") == "telescope":
            parts.append("</ul><h2>Telescope candidates</h2>")
            parts.append(
                '<p class="naked-eye-notes">Each listed target passed the local '
                'altitude, darkness, and Moon checks. These are candidates, not a '
                'guarantee of visibility; sky quality and equipment matter.</p>'
            )
        else:
            parts.append("</ul>")
        parts.append('<h2>Room notes</h2><div class="notes"></div>')
    else:
        parts.append(
            f'<p class="stop-source">{_e(data["stops_label"])}</p>'
            '<h2>Planned stops</h2><ul class="list">'
        )
        for stop_line in data["stops"]:
            parts.append(_natsu_stop(stop_line))
        if not data["stops"]:
            parts.append("<li>No valid stops are available.</li>")
        parts.extend(
            [
                "</ul>",
                f'<p class="intro">{_e(data["intro"])}</p>',
                '<p class="safety">Stop moving before you look up.</p>',
            ]
        )

    juvia_has_timeline_pass = mode == "juvia" and any(
        row["iss_passes"] for row in data["timeline"]
    )
    if not juvia_has_timeline_pass:
        parts.append(_iss_section(data["iss_passes"]))
    parts.append("</main></body></html>")
    return "\n".join(parts)
