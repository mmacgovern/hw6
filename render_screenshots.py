"""Problem 5: save screenshots of what a PERSON sees for each practice document.

Run with:  .venv\\Scripts\\python.exe render_screenshots.py

- HTML: rendered in headless Microsoft Edge.
- Email: shown the way an email app does (headers + the HTML part if there is
  one, otherwise the plain text), then rendered in headless Edge.
- PDF: each page rendered to an image with pypdfium2.
Images go to output/screenshots/.
"""

import email
import html
import shutil
import subprocess
import sys
import tempfile
import time
from email import policy
from pathlib import Path

import pypdfium2

HERE = Path(__file__).parent
DOCS = sorted((HERE / "data" / "practice_docs").iterdir())
SHOTS = HERE / "output" / "screenshots"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def edge_screenshot(page: Path, out: Path, height: int = 800) -> None:
    # Edge's --screenshot fails silently on paths with spaces (like this OneDrive folder),
    # so it saves into a temp folder first. A throwaway profile stops it handing the
    # job to an already-open Edge window.
    work = Path(tempfile.gettempdir()) / "hw6_edge"
    work.mkdir(exist_ok=True)
    tmp_png = work / "shot.png"
    tmp_png.unlink(missing_ok=True)
    subprocess.run(
        [str(EDGE), "--headless", "--disable-gpu", "--hide-scrollbars",
         f"--user-data-dir={work / 'profile'}",
         f"--window-size=900,{height}", f"--screenshot={tmp_png}", page.resolve().as_uri()],
        check=True, capture_output=True, timeout=60,
    )
    # Edge can return before its background process finishes writing the file.
    for _ in range(60):
        if tmp_png.exists() and tmp_png.stat().st_size > 0:
            shutil.move(tmp_png, out)
            return
        time.sleep(0.5)
    raise RuntimeError(f"Edge did not save {out.name}")


def email_view(path: Path) -> str:
    """Build the page an email app would show for this message."""
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    headers = "".join(
        f"<div><b>{h}:</b> {html.escape(str(msg[h]))}</div>"
        for h in ("From", "To", "Subject", "Date") if msg[h]
    )
    part = msg.get_body(preferencelist=("html", "plain"))
    body = part.get_content()
    if part.get_content_type() != "text/html":
        body = f"<pre style='font-family:inherit;white-space:pre-wrap'>{html.escape(body)}</pre>"
    return (
        "<!doctype html><html><head><meta charset='utf-8'></head>"
        "<body style='font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222'>"
        f"<div style='border-bottom:1px solid #ccc;padding-bottom:10px;margin-bottom:14px'>{headers}</div>"
        f"{body}</body></html>"
    )


def main() -> None:
    if not EDGE.exists():
        sys.exit(f"Microsoft Edge not found at {EDGE}")
    SHOTS.mkdir(parents=True, exist_ok=True)
    tmp = SHOTS / "_email_views"
    tmp.mkdir(exist_ok=True)
    for doc in DOCS:
        stem = doc.stem
        if doc.suffix == ".html":
            edge_screenshot(doc, SHOTS / f"{stem}.png")
        elif doc.suffix == ".eml":
            view = tmp / f"{stem}.html"
            view.write_text(email_view(doc), encoding="utf-8")
            edge_screenshot(view, SHOTS / f"{stem}.png", height=600)
        elif doc.suffix == ".pdf":
            pdf = pypdfium2.PdfDocument(str(doc))
            for i, page in enumerate(pdf, start=1):
                page.render(scale=1.5).to_pil().save(SHOTS / f"{stem}_page{i}.png")
        print("saved", stem)


if __name__ == "__main__":
    main()
