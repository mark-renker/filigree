"""Gauntlet Loop status page generator.

The ledger (status/ledger.json) is the single record of the loop:
every piece, every round, every verdict, and which artifact is currently the
ratcheted best.  Regenerate the page with:

    python tools/gauntlet_status.py

    # or append a verdict:
    python tools/gauntlet_status.py --piece P4 --round 2 \
        --verdict CANDIDATE --reason "..." --evidence "tests/test_mpe.py"
"""

from __future__ import annotations

import argparse
import html
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "status", "ledger.json")
PAGE = os.path.join(ROOT, "status", "gauntlet-status.html")

CSS = """
:root{--bg:#0c0d10;--panel:#14161b;--line:#23262e;--fg:#e6e8ee;--dim:#8a90a0;
--win:#57d9a3;--loss:#ff6b6b;--invalid:#f7b955;--accent:#8ab4ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;padding:28px}
h1{font-size:19px;margin:0 0 4px;letter-spacing:.02em}
.sub{color:var(--dim);margin-bottom:22px;font-size:12px}
.brake{color:var(--invalid);border:1px solid var(--invalid);padding:2px 7px;border-radius:3px;
font-size:11px;margin-left:8px}
table{width:100%;border-collapse:collapse;margin-bottom:26px}
th{text-align:left;color:var(--dim);font-weight:400;font-size:11px;text-transform:uppercase;
letter-spacing:.08em;border-bottom:1px solid var(--line);padding:6px 10px}
td{border-bottom:1px solid var(--line);padding:8px 10px;vertical-align:top}
tr:hover td{background:#11131a}
.piece{color:var(--accent)}
.v-CANDIDATE{color:var(--win)} .v-REFERENCE{color:var(--loss)} .v-INVALID{color:var(--invalid)}
.badge{display:inline-block;padding:1px 7px;border-radius:3px;font-size:11px;
border:1px solid currentColor}
.reason{color:var(--fg);max-width:640px}
.ev{color:var(--dim);font-size:12px}
.best{background:#0f1a16}
.legend{color:var(--dim);font-size:12px;border-top:1px solid var(--line);padding-top:14px}
code{background:#1b1e26;padding:1px 5px;border-radius:3px}
"""


def load() -> dict:
    if os.path.exists(LEDGER):
        with open(LEDGER, encoding="utf-8") as fh:
            return json.load(fh)
    return {"pieces": {}, "rounds": []}


def save(data: dict) -> None:
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def render(data: dict) -> str:
    rows = []
    # Rounds are appended in the order they were judged, which is not the order a
    # reader wants: a critic round backfilled after the fix it caused would appear
    # below it.  Present them grouped by piece, in round order.
    for r in sorted(data["rounds"], key=lambda r: (r.get("piece", ""), r.get("round", 0))):
        v = r.get("verdict", "INVALID")
        cls = f"v-{v}"
        rows.append(
            "<tr class='{best}'><td class='piece'>{piece}</td><td>{rnd}</td>"
            "<td><span class='badge {cls}'>{v}</span></td>"
            "<td class='reason'>{reason}</td><td class='ev'>{ev}</td>"
            "<td class='ev'>{when}</td></tr>".format(
                best="best" if r.get("became_best") else "",
                piece=html.escape(str(r.get("piece", ""))),
                rnd=html.escape(str(r.get("round", ""))),
                cls=cls, v=html.escape(v),
                reason=html.escape(str(r.get("reason", ""))),
                ev=html.escape(str(r.get("evidence", ""))),
                when=html.escape(str(r.get("when", ""))),
            )
        )
    prows = []
    for name, p in sorted(data["pieces"].items()):
        prows.append(
            "<tr><td class='piece'>{n}</td><td>{title}</td><td>{bar}</td>"
            "<td>{rounds}</td><td class='v-CANDIDATE'>{best}</td><td>{state}</td></tr>".format(
                n=html.escape(name), title=html.escape(p.get("title", "")),
                bar=html.escape(p.get("bar", "")), rounds=p.get("rounds", 0),
                best=html.escape(p.get("best", "—")), state=html.escape(p.get("state", "")),
            )
        )
    return f"""<!doctype html><meta charset="utf-8">
<title>Filigree — Gauntlet Loop status</title><style>{CSS}</style>
<h1>Filigree — Gauntlet Loop status<span class="brake">the user is the brake</span></h1>
<div class="sub">generated {time.strftime('%Y-%m-%d %H:%M:%S')} · ledger
<code>status/ledger.json</code> · bar <code>refs/BAR.md</code> · exit = candidate wins the
blind comparison, or you stop the run</div>

<table><tr><th>piece</th><th>what</th><th>bar</th><th>rounds</th><th>ratcheted best</th>
<th>state</th></tr>{''.join(prows)}</table>

<table><tr><th>piece</th><th>round</th><th>verdict</th><th>specific reason</th>
<th>evidence</th><th>when</th></tr>{''.join(rows)}</table>

<div class="legend">verdict <span class="badge v-CANDIDATE">CANDIDATE</span> = our artifact won
the blind pick · <span class="badge v-REFERENCE">REFERENCE</span> = the bar won, builder goes
again · <span class="badge v-INVALID">INVALID</span> = evidence was broken, round discarded,
previous best stands (ratchet).</div>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--piece")
    ap.add_argument("--round", type=int)
    ap.add_argument("--verdict", choices=["CANDIDATE", "REFERENCE", "INVALID"])
    ap.add_argument("--reason", default="")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--became-best", action="store_true")
    ap.add_argument("--set-piece", nargs=4, metavar=("NAME", "TITLE", "BAR", "STATE"))
    args = ap.parse_args()

    data = load()
    if args.set_piece:
        name, title, bar, state = args.set_piece
        p = data["pieces"].setdefault(name, {})
        p.update({"title": title, "bar": bar, "state": state})
        p.setdefault("rounds", 0)
        p.setdefault("best", "—")
    if args.piece and args.verdict:
        data["rounds"].append({
            "piece": args.piece, "round": args.round, "verdict": args.verdict,
            "reason": args.reason, "evidence": args.evidence,
            "became_best": args.became_best,
            "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        p = data["pieces"].setdefault(args.piece, {"title": "", "bar": "", "state": "running"})
        p["rounds"] = max(p.get("rounds", 0), args.round or 0)
        if args.became_best:
            p["best"] = f"round {args.round}"
    save(data)
    os.makedirs(os.path.dirname(PAGE), exist_ok=True)
    with open(PAGE, "w", encoding="utf-8") as fh:
        fh.write(render(data))
    print(f"wrote {PAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
