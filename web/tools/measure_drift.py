#!/usr/bin/env python3
"""Measure textarea/overlay horizontal drift in the Filigree playground editor.

The playground's glyph lanes are column-aligned: a bend written under beat 3 of a
`notes` lane must sit over beat 3.  The syntax overlay is a separate element
stacked on the textarea, so any per-character rounding difference accumulates
left-to-right and shears the whole document.  Round 1 of the UI review measured
~53 px (about seven characters) of drift on a 4000-character lane.

This script loads the real page, types single lanes of 100 / 1000 / 4000
characters, and compares the x position of the LAST character as the browser
lays it out in the textarea versus in the overlay.  Usage:

    PYTHONPATH=src python -m filigree.cli serve --port 8793 &
    python web/tools/measure_drift.py --url http://localhost:8793/

Exit status is non-zero if drift at 4000 characters exceeds --tolerance px
(default 1.0), so this doubles as a regression gate.  Requires Playwright; it is
a development tool and is not part of the shipped `web/` payload.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# JS: build a lane of N characters, then measure the same character index in the
# textarea (via a mirror div using getComputedStyle) and in the overlay (via the
# real rendered token span), and report the difference.
MEASURE_JS = r"""
async (n) => {
  const ta = document.getElementById('ta');
  const hl = document.getElementById('hl');

  // one long single-line lane: bar separators every 8 chars keeps it realistic
  let lane = 'notes  | ';
  while (lane.length < n) lane += (lane.length % 9 === 8) ? '| ' : 'c4 ';
  lane = lane.slice(0, n);

  ta.value = lane;
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

  const cs = getComputedStyle(ta);
  // Mirror the textarea's own text metrics exactly.
  const probe = document.createElement('span');
  probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre;top:-9999px;left:0';
  probe.style.font = cs.font;
  probe.style.fontFamily = cs.fontFamily;
  probe.style.fontSize = cs.fontSize;
  probe.style.letterSpacing = cs.letterSpacing;
  probe.style.tabSize = cs.tabSize;
  document.body.appendChild(probe);
  probe.textContent = lane;
  const taEnd = probe.getBoundingClientRect().width;
  probe.remove();

  // The overlay's rightmost painted edge for the same line.
  const line = hl.querySelector('.ln') || hl;
  const toks = line.querySelectorAll('.tk');
  const lb = line.querySelector('.lb');
  const base = (lb || line).getBoundingClientRect().left;
  let ovEnd = 0;
  toks.forEach(t => {
    const r = t.getBoundingClientRect();
    ovEnd = Math.max(ovEnd, r.right - base);
  });

  return {
    n,
    chars: lane.length,
    textareaEnd: taEnd,
    overlayEnd: ovEnd,
    drift: ovEnd - taEnd,
    tokenSpans: toks.length,
    perCharSpans: toks.length >= lane.length * 0.5,
    scrollWidthDelta: hl.scrollWidth - ta.scrollWidth,
    overlayText: (lb ? lb.textContent : '') === lane,
  };
}
"""


def _chrome() -> str | None:
    """Prefer a full chromium build if the headless shell was not downloaded."""
    import glob

    hits = sorted(glob.glob(
        os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")))
    return hits[-1] if hits else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8793/")
    ap.add_argument("--tolerance", type=float, default=1.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed; skipping drift measurement", file=sys.stderr)
        return 0

    rows = []
    with sync_playwright() as p:
        b = p.chromium.launch(
            executable_path=_chrome(),
            args=["--autoplay-policy=no-user-gesture-required"],
        )
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(args.url, wait_until="load")
        pg.wait_for_timeout(900)
        for n in (100, 1000, 4000):
            rows.append(pg.evaluate(MEASURE_JS, n))
        b.close()

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{'chars':>7} {'textarea px':>12} {'overlay px':>11} {'drift px':>9} {'spans':>6}")
        for r in rows:
            print(
                f"{r['chars']:>7} {r['textareaEnd']:>12.3f} {r['overlayEnd']:>11.3f} "
                f"{r['drift']:>+9.3f} {r['tokenSpans']:>6}"
            )

    worst = max(abs(r["drift"]) for r in rows)
    last = rows[-1]
    bad = []
    if abs(last["drift"]) > args.tolerance:
        bad.append(f"drift {last['drift']:+.3f}px at {last['chars']} chars > {args.tolerance}px")
    if last["perCharSpans"]:
        bad.append("overlay is emitting roughly one span per character")
    if not last["overlayText"]:
        bad.append("overlay base text does not match the textarea exactly")
    if bad:
        print("FAIL: " + "; ".join(bad), file=sys.stderr)
        return 1
    print(f"OK: worst |drift| = {worst:.3f}px (tolerance {args.tolerance}px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
