"""Optionally render demo cards with Chrome and report PDF page counts."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from zoneinfo import ZoneInfo

import main


def _find_chrome() -> str | None:
    executable = shutil.which("chrome") or shutil.which("chrome.exe")
    if executable:
        return executable
    roots = (
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
    )
    for root in roots:
        if root:
            candidate = Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def _pdf_page_count(path: Path) -> int:
    contents = path.read_bytes()
    return len(re.findall(rb"/Type\s*/Page\b", contents))


def main_check() -> int:
    chrome = _find_chrome()
    if chrome is None:
        print("Chrome was not found; print page check skipped.")
        return 0

    failed = False
    with tempfile.TemporaryDirectory(prefix="sky-quest-print-check-") as temp:
        root = Path(temp)
        for mode in ("lucy", "juvia", "natsu"):
            for depth in ("casual", "explorer", "deep"):
                card_dir = root / f"{mode}-{depth}"
                try:
                    card_path = main.print_card(
                        main.DEMO_LATITUDE,
                        main.DEMO_LONGITUDE,
                        main.DEMO_TIME.replace(
                            tzinfo=ZoneInfo(main.config.TIMEZONE)
                        ),
                        mode=mode,
                        demo=True,
                        output_dir=card_dir,
                        depth=depth,
                    )
                    pdf_path = root / f"{mode}-{depth}.pdf"
                    result = subprocess.run(
                        [
                            chrome,
                            "--headless=new",
                            "--disable-gpu",
                            "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf_path}",
                            card_path.resolve().as_uri(),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        check=False,
                    )
                    if result.returncode != 0 or not pdf_path.is_file():
                        failed = True
                        print(f"{mode}/{depth}: Chrome failed to create a PDF.")
                        continue
                    pages = _pdf_page_count(pdf_path)
                    print(f"{mode}/{depth}: {pages} page(s)")
                    if pages != 1:
                        failed = True
                except (OSError, ValueError, FileNotFoundError, subprocess.TimeoutExpired) as error:
                    failed = True
                    print(f"{mode}/{depth}: check failed ({type(error).__name__}).")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main_check())
