"""Export docs/USER_MANUAL.md and docs/TECHNICAL_REPORT.md to PDF (Markdown -> HTML -> Chrome print).
    .venv/bin/python docs/build_pdfs.py            # both
    .venv/bin/python docs/build_pdfs.py USER_MANUAL
Needs the `markdown` package and Google Chrome (macOS path below, or CHROME=<path>).
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

CSS = """<style>
body{font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;font-size:11pt;line-height:1.5;color:#111;max-width:820px;margin:0 auto;padding:24px 12px}
h1{font-size:22pt;margin:0 0 6pt}h2{font-size:15pt;margin:22pt 0 6pt;border-bottom:1px solid #ccc;padding-bottom:3pt}h3{font-size:12pt;margin:14pt 0 4pt}
code{font-family:Menlo,Consolas,monospace;font-size:9.5pt;background:#f2f2f2;padding:0 3px}pre{background:#f4f4f4;padding:8px;font-size:9pt;overflow-x:auto;white-space:pre-wrap}
table{border-collapse:collapse;width:100%;font-size:9.5pt;margin:8pt 0}th,td{border:1px solid #ccc;padding:4px 6px;text-align:left;vertical-align:top}th{background:#eee}
p,li{max-width:none}@page{size:A4;margin:16mm 14mm}
</style>"""
DOCS = Path(__file__).resolve().parent


def chrome() -> str:
    for c in (os.environ.get("CHROME"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chrome")):
        if c and Path(c).exists():
            return c
    sys.exit("Chrome not found; set CHROME=<path to chrome binary>")


def build(name: str) -> None:
    md = io.open(DOCS / f"{name}.md", encoding="utf-8").read()
    html = markdown.markdown(md, extensions=["tables", "fenced_code"])
    tmp = DOCS / f"{name}.html"
    io.open(tmp, "w", encoding="utf-8").write(
        f"<!doctype html><html><head><meta charset='utf-8'><title>{name}</title>{CSS}</head><body>{html}</body></html>")
    try:
        subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={DOCS / (name + '.pdf')}", tmp.as_uri()],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"{name}.pdf  {(DOCS / (name + '.pdf')).stat().st_size} bytes")


if __name__ == "__main__":
    for n in sys.argv[1:] or ("USER_MANUAL", "TECHNICAL_REPORT"):
        build(n)
