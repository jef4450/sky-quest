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
.lucy h1 { margin-bottom: 1mm; }
.lucy h2 { margin: 1.5mm 0 .5mm; font-size: 22pt; }
.lucy .window { margin: 1mm 0; padding: 2mm; }
.lucy .window-label { font-size: 16pt; }
.lucy .window-time { font-size: 32pt; }
.lucy .picks { margin: 0; padding-left: 7mm; list-style: none; counter-reset: pick; }
.lucy .pick-row { display: grid; grid-template-columns: 7mm 1fr; gap: 1.5mm; align-items: center; padding: 1mm 1mm; border-bottom: 1pt solid #111; font-size: 14pt; line-height: 1.2; break-inside: avoid; page-break-inside: avoid; }
.lucy .pick-row { counter-increment: pick; position: relative; }
.lucy .pick-row::before { content: counter(pick) "."; position: absolute; left: -6mm; font-weight: 700; }
.lucy .pick-row.no-checkbox { grid-template-columns: 1fr; }
.lucy .pick-detail { display: block; }
.lucy .pick-time { display: block; margin-top: .3mm; font-size: 14pt; font-weight: 700; }
.lucy .box { width: 6mm; height: 6mm; }
.lucy .guide-box { margin-top: 1mm; padding: 1.5mm 2mm; border: 1.5pt solid #111; break-inside: avoid; page-break-inside: avoid; }
.lucy .guide-box h2 { margin: 0 0 .5mm; }
.lucy .guide-list { margin: 0; padding-left: 5mm; }
.lucy .guide-item { margin: .5mm 0; font-size: 14pt; line-height: 1.2; break-inside: avoid; }
.lucy .iss { margin-top: 1mm; padding: 1.5mm 2mm; font-size: 14pt; }
.lucy .intro { margin: 1mm 0; font-size: 14pt; line-height: 1.25; }
.lucy .small { margin-top: 1mm; font-size: 14pt; }
.lucy.depth-deep { font-size: 12pt; }
.lucy.depth-deep .picks { display: grid; grid-template-columns: 1fr 1fr; column-gap: 4mm; }
.lucy.depth-deep .pick-row { font-size: 12pt; grid-template-columns: 5mm 1fr; gap: 1mm; padding: .8mm; }
.lucy.depth-deep .pick-time { font-size: 12pt; }
.lucy.depth-deep .box { width: 4.5mm; height: 4.5mm; }
.lucy.depth-deep .guide-item { font-size: 12pt; }
.lucy.depth-explorer h1,
.lucy.depth-deep h1 { margin-bottom: .5mm; }
.lucy.depth-explorer h2,
.lucy.depth-deep h2 { margin: .5mm 0 .25mm; }
.lucy.depth-explorer .window,
.lucy.depth-deep .window { margin: .5mm 0; padding: 1mm; }
.lucy.depth-explorer .window-time,
.lucy.depth-deep .window-time { margin-top: 0; line-height: 1; }
.lucy.depth-explorer .pick-row,
.lucy.depth-deep .pick-row {
    gap: 1mm;
    padding: .4mm .5mm;
    line-height: 1.05;
}
.lucy.depth-explorer .pick-time,
.lucy.depth-deep .pick-time { margin-top: 0; line-height: 1.05; }
.lucy.depth-explorer .guide-box,
.lucy.depth-deep .guide-box { margin-top: .5mm; padding: .75mm 1mm; }
.lucy.depth-explorer .guide-item,
.lucy.depth-deep .guide-item { margin: .2mm 0; line-height: 1.05; }
.lucy.depth-explorer .iss,
.lucy.depth-deep .iss { margin-top: .5mm; padding: .75mm 1mm; }
.lucy.depth-explorer .intro,
.lucy.depth-deep .intro { margin: .5mm 0; line-height: 1.1; }
.lucy.depth-explorer .small,
.lucy.depth-deep .small { margin-top: .5mm; }
.juvia { font-size: 14pt; }
.juvia .intro { font-size: 14pt; }
.juvia .facing { font-size: 14pt; }
.juvia .timeline-item { font-size: 14pt; }
.juvia .telescope-candidate { font-size: 14pt; }
.juvia .naked-eye-notes { font-size: 14pt; }
.juvia .iss { font-size: 14pt; }
.juvia .notes { height: 25mm; }
.juvia.depth-deep { font-size: 12pt; }
.juvia.depth-deep .timeline { display: grid; grid-template-columns: 1fr 1fr; gap: 0 4mm; }
.juvia.depth-deep .timeline-item { font-size: 12pt; }
.juvia.depth-deep .telescope-candidate,
.juvia.depth-deep .naked-eye-notes,
.juvia.depth-deep .iss { font-size: 11pt; }
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
    depth = data.get("depth", "casual")
    if mode in {"lucy", "juvia"} and depth not in {
        "casual", "explorer", "deep"
    }:
        raise ValueError("depth must be casual, explorer, or deep")

    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Sky Quest - {_e(data['title'])}</title>",
        f"<style>{_BASE_STYLE}</style></head>",
        (
            f'<body><main class="card {mode}'
            + (
                f' depth-{_e(data.get("depth", "casual"))}'
                if mode in {"lucy", "juvia"}
                else ""
            )
            + '">'
        ),
        _header(data, mode),
    ]

    if mode == "lucy":
        parts.append("<section><h2>Tonight's top picks</h2><ol class=\"picks\">")
        for pick in data.get("top_picks", []):
            checkbox = (
                '<span class="box" aria-label="unchecked"></span>'
                if pick.get("checkable", False)
                else ""
            )
            no_checkbox = "" if checkbox else " no-checkbox"
            if pick.get("note"):
                detail = _e(pick["note"])
            elif pick["category"] == "iss":
                detail = (
                    f'ISS: {_e(pick["direction"])}, {_e(pick["height"])}'
                    if pick.get("height")
                    else f'ISS: {_e(pick["direction"])}'
                )
            else:
                detail = (
                    f'{_e(pick["object"])}: {_e(pick["direction"])}, '
                    f'{_e(pick["height"])}'
                )
            parts.append(
                f'<li class="pick-row{no_checkbox}">{checkbox}<span>'
                f'<span class="pick-detail">{detail}</span>'
                f'<span class="pick-time">Best time: {_e(pick["best_time"])}</span>'
                "</span></li>"
            )
        if not data.get("top_picks"):
            parts.append(
                '<li class="pick-row no-checkbox">Nothing above the horizon is available tonight.</li>'
            )
        parts.append("</ol></section>")
        parts.append('<section class="guide-box"><h2>How to find it</h2><ul class="guide-list">')
        for guide in data.get("guides", []):
            parts.append(f'<li class="guide-item">{_e(guide["text"])}</li>')
        if not data.get("guides"):
            parts.append(
                '<li class="guide-item">No constellation guide is available from the visible anchors tonight.</li>'
            )
        parts.append("</ul></section>")
        parts.append(_iss_section(data["iss_passes"]))
        parts.append(f'<p class="intro">{_e(data["intro"])}</p>')
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
    if mode == "natsu" or (mode == "juvia" and not juvia_has_timeline_pass):
        parts.append(_iss_section(data["iss_passes"]))
    parts.append("</main></body></html>")
    return "\n".join(parts)
