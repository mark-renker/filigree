"""Tests for piece P6 — the browser playground (`web/**`).

Three jobs:

1. `web/fixtures/score.json` must be a byte-for-byte valid `ir.Score.to_json()`
   payload.  We prove it by *rebuilding* the frozen IR dataclasses from the
   fixture and asserting `Score.to_json()` reproduces the file exactly — so the
   front end can never drift from the compiler's real output shape.
2. Every file the app needs must exist (a zero-build static app: no npm, no
   bundler, no lockfile).
3. No external network URL may appear in the shipped HTML/CSS/JS.  The
   playground has to work fully offline from the fixture.
"""

from __future__ import annotations

import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
WEB = os.path.join(ROOT, "web")
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from filigree import ir  # noqa: E402

FIXTURE = os.path.join(WEB, "fixtures", "score.json")

REQUIRED_FILES = [
    "index.html",
    "style.css",
    "app.js",
    "editor.js",
    "synth.js",
    os.path.join("fixtures", "score.json"),
    os.path.join("fixtures", "source.fil"),
]

# Files that ship to the browser. web/tools/ is dev-only tooling and excluded.
SHIPPED_EXT = (".html", ".js", ".css")
DEV_DIRS = {"tools", "__pycache__", "node_modules"}


def shipped_files() -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(WEB):
        dirnames[:] = [d for d in dirnames if d not in DEV_DIRS]
        for fn in filenames:
            if fn.endswith(SHIPPED_EXT):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


@pytest.fixture(scope="module")
def fixture_json() -> dict:
    with open(FIXTURE) as fh:
        return json.load(fh)


# ── 1. required files ───────────────────────────────────────────────────────

@pytest.mark.parametrize("rel", REQUIRED_FILES)
def test_required_file_exists(rel):
    path = os.path.join(WEB, rel)
    assert os.path.isfile(path), "missing " + rel
    assert os.path.getsize(path) > 200, rel + " is suspiciously small"


def test_zero_build_no_package_manifest():
    """A zero-build app: no npm manifest, no lockfile, no bundler config."""
    for bad in ("package.json", "package-lock.json", "yarn.lock",
                "pnpm-lock.yaml", "webpack.config.js", "vite.config.js",
                "node_modules"):
        assert not os.path.exists(os.path.join(WEB, bad)), \
            "web/ must stay build-free, found " + bad


def test_html_references_all_scripts():
    html = open(os.path.join(WEB, "index.html")).read()
    for asset in ("style.css", "app.js", "editor.js", "synth.js"):
        assert asset in html, "index.html does not load " + asset


# ── 2. no external network URLs ─────────────────────────────────────────────

URL_RE = re.compile(r"""(?:https?:)?//[A-Za-z0-9\-.]+\.[A-Za-z]{2,}""")
# `//` inside a JS line comment or a regex is not a URL; require a dot-domain.
ALLOWED = re.compile(r"^//(?:www\.)?w3\.org$")   # nothing is allowed, kept explicit

# An `xmlns="http://www.w3.org/2000/svg"` is an XML *namespace identifier*, not a
# resource the browser fetches: SVG markup is inert without the declaration and
# no request is ever made for that URI.  The real invariant this test defends is
# "the playground loads zero external resources", so namespace-only URI forms are
# excluded by matching the attribute they appear in -- NOT by widening the host
# allowlist, which would also have let through a real fetch from w3.org.
XMLNS_URI_RE = re.compile(
    r"""xmlns(?::[A-Za-z0-9_-]+)?\s*=\s*['"]?(?:https?:)?//[^'"\s>)]*""")


def _strip_xml_namespaces(line: str) -> str:
    return XMLNS_URI_RE.sub("xmlns=NS", line)


@pytest.mark.parametrize("path", shipped_files(), ids=lambda p: os.path.relpath(p, WEB))
def test_no_external_urls(path):
    text = open(path, encoding="utf-8").read()
    hits = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("*") or stripped.startswith("//"):
            continue                      # comment lines
        for m in URL_RE.finditer(_strip_xml_namespaces(line)):
            frag = m.group(0)
            if ALLOWED.match(frag):
                continue
            hits.append(frag)
    assert not hits, os.path.relpath(path, WEB) + " references external URLs: " + repr(hits)


def test_xmlns_exclusion_does_not_hide_a_real_fetch():
    """The namespace carve-out must not become a hole for real network loads."""
    assert not URL_RE.search(_strip_xml_namespaces('xmlns="http://www.w3.org/2000/svg"'))
    still = _strip_xml_namespaces('<script src="https://cdn.evil.example.com/x.js"></script>')
    assert URL_RE.search(still), "a real external src must still be flagged"
    mixed = _strip_xml_namespaces(
        '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://x.example.org/a"/>')
    assert URL_RE.search(mixed), "a namespace on the same line must not mask a real URL"


def test_every_load_target_is_same_origin():
    """State the real invariant directly, independent of the URL regex."""
    for path in shipped_files():
        text = open(path, encoding="utf-8").read()
        for m in re.finditer(r"""(?:\bsrc|\bhref|@import)\s*=?\s*['"]([^'"]*)['"]""", text):
            val = m.group(1)
            assert not val.startswith(("http://", "https://", "//")), (
                os.path.relpath(path, WEB) + " loads off-origin: " + val)


@pytest.mark.parametrize("path", shipped_files(), ids=lambda p: os.path.relpath(p, WEB))
def test_no_cdn_or_import_from_network(path):
    text = open(path, encoding="utf-8").read().lower()
    for bad in ("cdn.", "unpkg", "jsdelivr", "googleapis", "cdnjs",
                "esm.sh", "skypack", "@fontsource"):
        assert bad not in text, os.path.relpath(path, WEB) + " mentions " + bad


def test_api_base_is_configurable_and_relative():
    app = open(os.path.join(WEB, "app.js")).read()
    assert "window.FILIGREE_API" in app, "API base must come from window.FILIGREE_API"
    assert "/api/compile" in app, "app.js must POST to {base}/api/compile"
    assert "fixtures/score.json" in app, "app must be able to boot from the fixture"


# ── 3. the fixture is a real Score.to_json() payload ────────────────────────

def _rebuild(doc: dict) -> ir.Score:
    """Rebuild the frozen IR dataclasses from the fixture JSON."""
    score = ir.Score(
        tempo=doc["tempo"],
        meter=(doc["meter"][0], doc["meter"][1]),
        ppq=doc["ppq"],
        key=(doc["key"]["tonic"], doc["key"]["mode"]),
        bend_range=doc["bendRange"],
        title=doc["title"],
        warnings=list(doc["warnings"]),
    )
    for sd in doc["staves"]:
        st = ir.StaveIR(name=sd["name"])
        for cd in sd["chords"]:
            st.chords.append(ir.ChordEvent(
                start=cd["start"], dur=cd["dur"], symbol=cd["symbol"],
                root_pc=cd["rootPc"], quality=cd["quality"],
                pitches=list(cd["pitches"]), guide_tones=list(cd["guideTones"]),
                stave=sd["name"]))
        for nd in sd["notes"]:
            note = ir.Note(
                start=nd["start"], dur=nd["dur"], pitch=nd["pitch"],
                velocity=nd["velocity"], stave=sd["name"], voice=nd["voice"],
                detune=nd["detune"], channel=nd["channel"], id=nd["id"])
            for lane, pts in nd["curves"].items():
                # JSON `null` is the wire form of the IR's NaN gap sentinel
                note.curves[lane] = ir.Curve(
                    lane=lane,
                    points=[(p[0], float("nan") if p[1] is None else p[1])
                            for p in pts])
            st.notes.append(note)
        score.staves.append(st)
    return score


def test_fixture_roundtrips_through_ir_score(fixture_json):
    """The strongest possible schema check: rebuild -> to_json() -> identical."""
    rebuilt = _rebuild(fixture_json).to_json()
    assert rebuilt == fixture_json, "fixture does not match ir.Score.to_json() output"


def test_fixture_top_level_keys_match_schema(fixture_json):
    expected = set(ir.Score().to_json().keys())
    assert set(fixture_json.keys()) == expected


def test_fixture_stave_and_note_keys_match_schema(fixture_json):
    probe = ir.Score(staves=[ir.StaveIR(
        name="p",
        notes=[ir.Note(start=0.0, dur=1.0, pitch=60,
                       curves={ir.BEND: ir.Curve(ir.BEND, [(0.0, 0.0)])})],
        chords=[ir.ChordEvent(start=0.0, dur=1.0, symbol="i", root_pc=0,
                              quality="min")])]).to_json()
    st_keys = set(probe["staves"][0].keys())
    n_keys = set(probe["staves"][0]["notes"][0].keys())
    c_keys = set(probe["staves"][0]["chords"][0].keys())
    for sd in fixture_json["staves"]:
        assert set(sd.keys()) == st_keys
        for nd in sd["notes"]:
            assert set(nd.keys()) == n_keys
        for cd in sd["chords"]:
            assert set(cd.keys()) == c_keys


def test_fixture_units_and_ranges(fixture_json):
    doc = fixture_json
    assert 20 <= doc["tempo"] <= 400
    assert len(doc["meter"]) == 2
    assert 0 <= doc["key"]["tonic"] <= 11
    assert doc["bendRange"] > 0
    dur = doc["durationBeats"]
    assert dur > 0
    for sd in doc["staves"]:
        for nd in sd["notes"]:
            assert isinstance(nd["pitch"], int) and 0 <= nd["pitch"] <= 127
            assert 1 <= nd["velocity"] <= 127
            assert nd["dur"] > 0
            assert 0 <= nd["start"] <= dur
            for lane, pts in nd["curves"].items():
                assert lane in ir.LANE_RANGES, "unknown lane " + lane
                lo, hi = ir.LANE_RANGES[lane]
                if lane == "bend":
                    # a bend lane may widen its own drawn range with `!range=`; the
                    # hard ceiling is the score's MPE bend range
                    lo, hi = -doc["bendRange"], doc["bendRange"]
                assert len(pts) >= 2, "curve %s on note %s is degenerate" % (lane, nd["id"])
                beats = [p[0] for p in pts]
                assert beats == sorted(beats), "curve points must be sorted by beat"
                # exported beats are rounded to 5 decimals, so allow a rounding step
                assert beats[0] >= nd["start"] - 1e-4
                assert beats[-1] <= nd["start"] + nd["dur"] + 1e-4
                for _, v in pts:
                    if v is None:      # gap sentinel: "no data from here"
                        continue
                    assert lo - 1e-6 <= v <= hi + 1e-6, \
                        "%s value %r outside %r" % (lane, v, (lo, hi))


def test_fixture_duration_matches_notes(fixture_json):
    end = max(n["start"] + n["dur"]
              for s in fixture_json["staves"] for n in s["notes"])
    assert abs(end - fixture_json["durationBeats"]) < 1e-9


def test_fixture_note_ids_unique(fixture_json):
    ids = [n["id"] for s in fixture_json["staves"] for n in s["notes"]]
    assert len(ids) == len(set(ids))


# ── 4. the fixture is musically interesting enough to exercise the UI ───────

def test_fixture_is_eight_bars_three_staves(fixture_json):
    doc = fixture_json
    beats_per_bar = doc["meter"][0] * (4 / doc["meter"][1])
    # humanised timing moves the final note by a few milliseconds, so compare in
    # bars with a tolerance rather than exactly
    assert abs(doc["durationBeats"] / beats_per_bar - 8) < 0.02, \
        "expected 8 bars, got %.4f" % (doc["durationBeats"] / beats_per_bar)
    assert len(doc["staves"]) == 3, "expected 3 staves"


def test_fixture_has_chords_with_guide_tones(fixture_json):
    for sd in fixture_json["staves"]:
        assert len(sd["chords"]) == 8, sd["name"] + " should carry 8 chord events"
        for cd in sd["chords"]:
            assert cd["symbol"]
            assert len(cd["pitches"]) >= 3
            assert len(cd["guideTones"]) >= 2, "chord ribbon needs guide tones"
            for pc in cd["guideTones"]:
                assert 0 <= pc <= 11


def test_fixture_has_named_voices_and_chords(fixture_json):
    voices = set()
    for sd in fixture_json["staves"]:
        for nd in sd["notes"]:
            if nd["voice"]:
                voices.add(nd["voice"])
    assert len(voices) >= 4, "expected several named voices, got " + repr(voices)
    # simultaneous notes in one stave == a real chord to draw
    best = 0
    for sd in fixture_json["staves"]:
        starts = {}
        for nd in sd["notes"]:
            k = round(nd["start"], 4)
            starts[k] = starts.get(k, 0) + 1
        best = max([best] + list(starts.values()))
    assert best >= 3, "expected at least one 3-note chord somewhere in the score"


def test_every_note_carries_bend_press_and_timbre(fixture_json):
    total_points = 0
    for sd in fixture_json["staves"]:
        for nd in sd["notes"]:
            for lane in ("bend", "press", "timbre"):
                assert lane in nd["curves"], \
                    "note %s has no %s curve" % (nd["id"], lane)
                total_points += len(nd["curves"][lane])
    assert total_points > 2000, "curves are too coarse to be interesting"


def test_bend_curves_actually_move(fixture_json):
    moved = 0
    for sd in fixture_json["staves"]:
        for nd in sd["notes"]:
            vals = [v for _, v in nd["curves"]["bend"] if v is not None]
            if vals and max(vals) - min(vals) > 0.1:
                moved += 1
    total = sum(len(sd["notes"]) for sd in fixture_json["staves"])
    assert moved >= 0.7 * total, \
        "only %d of %d notes have a moving bend curve" % (moved, total)


def test_default_document_compiles_clean(fixture_json):
    """LEAD RULING (round 3): the document a first-time visitor lands on must be
    exemplary, so it carries no warnings at all.  The diagnostics panel is exercised
    by `web/fixtures/diagnostics.fil` instead."""
    assert fixture_json["warnings"] == [], fixture_json["warnings"]


def test_diagnostics_fixture_produces_prefixed_warnings():
    """The panel still needs a shipped document that shows it working."""
    from filigree import parse as _parse

    path = os.path.join(WEB, "fixtures", "diagnostics.fil")
    assert os.path.exists(path), "the diagnostics demo document is missing"
    doc = _parse.parse(open(path).read(), path)
    assert doc.warnings, "the diagnostics panel needs something to show"
    for w in doc.warnings:
        assert re.match(r"^[^\s:]+:\d+:\d+:\s", w), \
            "warning is not file:line:col prefixed: " + w


# ── 5. the paired source is plausible Filigree and column-aligned ──────────

def test_source_fil_exists_and_matches_the_score(fixture_json):
    src = open(os.path.join(WEB, "fixtures", "source.fil")).read()
    assert "@tempo" in src and "84bpm" in src
    assert "@key    C minor" in src
    for name in [s["name"] for s in fixture_json["staves"]]:
        assert "stave " + name + " {" in src, "source.fil lacks stave " + name
    for lane in ("harm", "notes", "bend", "press", "timbre", "voices"):
        assert re.search(r"^\s*" + lane, src, re.M), "source.fil lacks a " + lane + " lane"
    assert ">3" in src, "source.fil should show a harmonic-resolve target"


def test_source_lane_columns_are_aligned():
    """The whole pitch of Filigree: curve glyphs line up under their notes."""
    lines = open(os.path.join(WEB, "fixtures", "source.fil")).read().splitlines()
    blocks, cur = [], []
    for ln in lines:
        # any lane may carry a `!option=value` suffix (e.g. `bend!range=6st`)
        m = re.match(r"^  (harm|notes|bend|press|timbre)(?:!\S+)?\s*\|", ln)
        if m:
            cur.append(ln)
        elif cur:
            blocks.append(cur); cur = []
    if cur:
        blocks.append(cur)
    assert blocks, "no lane blocks found in source.fil"
    aligned = 0
    for blk in blocks:
        if len(blk) < 4:
            continue
        cols = [[i for i, ch in enumerate(ln) if ch == "|"] for ln in blk]
        # only blocks whose lanes share a bar count can be expected to align
        if len(set(len(c) for c in cols)) != 1:
            continue
        assert all(c == cols[0] for c in cols), \
            "bar separators are not column-aligned in block:\n" + "\n".join(blk)
        aligned += 1
    assert aligned >= 2, "expected at least two fully column-aligned lane blocks"


def test_no_line_is_absurdly_long():
    src = open(os.path.join(WEB, "fixtures", "source.fil")).read()
    for i, ln in enumerate(src.splitlines(), 1):
        assert len(ln) <= 92, "source.fil:%d is %d chars (won't fit the editor pane)" % (i, len(ln))


# ── 6. round-2 UI review regressions ───────────────────────────────────────
#
# Each test below pins a defect found by the independent UI critic in round 1
# (refs/verdicts/P6_round1.md) so it cannot silently come back.

def _read(name: str) -> str:
    return open(os.path.join(WEB, name), encoding="utf-8").read()


def _srgb(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lum(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _srgb(r) + 0.7152 * _srgb(g) + 0.0722 * _srgb(b)


def contrast(fg: str, bg: str) -> float:
    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _css_var(css: str, name: str) -> str:
    m = re.search(re.escape("--" + name) + r"\s*:\s*(#[0-9a-fA-F]{3,8})", css)
    assert m, "style.css does not define --" + name
    return m.group(1)


def test_contrast_helper_matches_known_values():
    """Sanity-check the helper against WCAG reference pairs before trusting it."""
    assert contrast("#ffffff", "#000000") == pytest.approx(21.0, abs=0.01)
    assert contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.05)


def test_bar_separators_reach_wcag_aa():
    """D1: the `|` lane separators were measured at 1.84:1 -- unreadable.

    They define the lane columns, so they are load-bearing for reading the
    language, yet they must stay visually subordinate to the glyphs themselves.
    """
    css = _read("style.css")
    bg = _css_var(css, "bg1")
    struct = _css_var(css, "tk-struct")
    glyph = _css_var(css, "tk-glyph")
    assert contrast(struct, bg) >= 4.5, (
        "bar separators are " + str(round(contrast(struct, bg), 2)) + ":1")
    assert contrast(struct, bg) < contrast(glyph, bg), \
        "separators must stay subordinate to the glyphs"


def test_every_token_colour_reaches_wcag_aa():
    css = _read("style.css")
    bg = _css_var(css, "bg1")
    roles = re.findall(r"--tk-([a-z]+)\s*:\s*(#[0-9a-fA-F]{3,6})", css)
    assert roles, "no --tk-* token roles found"
    for name, col in roles:
        assert contrast(col, bg) >= 4.5, (
            "--tk-" + name + " is only " + str(round(contrast(col, bg), 2)) + ":1")


def test_token_palette_is_small():
    """D5: 22 distinct token colours read as noise; Strudel uses about four."""
    css = _read("style.css")
    roles = re.findall(r"--tk-[a-z]+\s*:\s*(#[0-9a-fA-F]{3,6})", css)
    distinct = {c.lower() for c in roles}
    assert len(distinct) <= 8, "token palette has " + str(len(distinct)) + " colours"
    # and the highlighter may only paint through those roles
    ed = _read("editor.js")
    assert "class=\"tk" in ed or "'tk " in ed or "tk " in ed


def test_editor_base_font_is_legible():
    """D5: 12px monospace lost a forced choice against Strudel's ~15px."""
    css = _read("style.css")
    m = re.search(r"--fs\s*:\s*(\d+(?:\.\d+)?)px", css)
    assert m, "style.css must define --fs for the editor base size"
    assert float(m.group(1)) >= 14, "editor base font is only " + m.group(1) + "px"
    m2 = re.search(r"--lh\s*:\s*(\d+(?:\.\d+)?)px", css)
    assert m2 and float(m2.group(1)) >= float(m.group(1)) * 1.3, \
        "line-height must leave the glyph lanes breathing room"


def test_focus_rings_exist():
    """D2: zero :focus rules meant a keyboard user could not see where they were."""
    css = _read("style.css")
    assert css.count(":focus") >= 5, "style.css has almost no :focus rules"
    assert ":focus-visible" in css
    assert "outline" in css
    focus = _css_var(css, "focus")
    assert contrast(focus, _css_var(css, "bg1")) >= 3.0, "focus ring is too dim to see"


def test_tab_key_is_not_an_unconditional_trap():
    """D1: editor.js swallowed every Tab, so focus could never leave the textarea."""
    ed = _read("editor.js")
    assert "Tab" in ed
    # there must be a path that returns WITHOUT preventing the default Tab
    assert re.search(r"leading|inLeading|_escaped|escaped", ed), \
        "Tab handling must be conditional on selection / leading whitespace / Escape"
    assert "Escape" in ed, "Escape must arm 'the next Tab leaves the editor'"


def test_controls_are_labelled_and_semantic():
    """D2: div-based buttons are invisible to keyboards and screen readers."""
    html = _read("index.html")
    assert html.count("aria-label") >= 8, "controls are not labelled"
    assert "<button" in html
    # sliders and toggles carry names too
    for control in ("zoom", "zoomY", "vol", "showCurves"):
        assert control in html
    app = _read("app.js")
    assert "<button" in app, "mute/solo must be real buttons, not styled spans"
    assert "aria-pressed" in app, "mute/solo are toggles and must expose their state"


def test_first_five_seconds_guidance_survives_narrow_widths():
    """D7: style.css:220 deleted the only hints below 1180px."""
    html = _read("index.html")
    assert "howto" in html, "index.html has no always-visible how-to strip"
    css = _read("style.css")
    assert "stepPlay" in html and "stepCompile" in html, \
        "the how-to strip must be actionable, not decorative text"
    # Inside every media query, the strip itself and its numbered steps must
    # survive.  (Its trailing prose explainer may be dropped when narrow -- the
    # three steps are the load-bearing part.)
    load_bearing = ("#howto", ".step", ".ph-hint")
    for block in re.findall(r"@media[^{]*\{(.*?)\n\}", css, re.S):
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", block):
            if "display" not in body or "none" not in body:
                continue
            for target in load_bearing:
                for part in sel.split(","):
                    part = part.strip()
                    if part == target or part.startswith(target + ":"):
                        raise AssertionError(target + " is hidden at some width: " + part)


def test_overlay_does_not_emit_one_span_per_character():
    """D3: per-character spans drifted ~1px/100 chars and sheared the columns."""
    ed = _read("editor.js")
    assert "ch'" in ed or "ch\"" in ed or "+ 'ch" in ed, \
        "tokens must be positioned in `ch` units so columns cannot accumulate error"
    assert "left:" in ed, "overlay tokens must be absolutely positioned by column"
    # a whole-line raw copy keeps the overlay's metrics identical to the textarea
    assert "lb" in ed


def test_overlay_and_textarea_share_metrics():
    css = _read("style.css")
    # tab-size must agree between the textarea, the overlay and editor.js
    tabs = set(re.findall(r"tab-size\s*:\s*(\d+)", css))
    assert tabs, "tab-size must be pinned so tabs cannot shift the overlay"
    assert len(tabs) == 1, "conflicting tab-size values: " + repr(tabs)
    ed = _read("editor.js")
    m = re.search(r"TAB\s*=\s*(\d+)", ed)
    assert m, "editor.js must know the tab width it is rendering against"
    assert m.group(1) == tabs.pop(), "editor.js TAB disagrees with CSS tab-size"
    assert "white-space:pre" in css.replace(" ", "").replace("\n", "") or \
        "white-space: pre" in css


def test_no_font_weight_changes_inside_the_glyph_lanes():
    """Bold runs make a monospace lane non-monospace in most font stacks."""
    css = _read("style.css")
    for block in re.findall(r"(#hl[^{}]*|\.tk[^{}]*)\{([^{}]*)\}", css):
        assert "font-weight" not in block[1], \
            "font-weight inside the overlay breaks monospacing: " + block[0].strip()


def test_a_failed_compile_does_not_revert_to_the_bundled_fixture():
    """A compiler error must never be shown as a silently different score."""
    app = _read("app.js")
    m = re.search(r"\.catch\(function \(err\) \{(.*?)\n    \}\);", app, re.S)
    assert m, "compile() must still have an error path"
    body = m.group(1)
    assert "setScore(S.fixture" not in body, \
        "the compile error path silently swaps in the bundled fixture"
    assert "S.stale" in body, "a failed compile must mark the roll as stale"


def test_compile_error_shapes_are_normalised():
    app = _read("app.js")
    assert "collectErrors" in app
    for shape in ("j.error", "j.errors", "j.detail", "j.diagnostics"):
        assert shape in app, "collectErrors does not handle " + shape


def test_diagnostics_jump_to_line_and_column():
    app = _read("app.js")
    assert re.search(r"gotoLine\(\s*[A-Za-z_.]+\.line\s*,\s*[A-Za-z_.]+\.col", app), \
        "clicking a diagnostic must jump to its line AND column"
    ed = _read("editor.js")
    assert re.search(r"gotoLine\s*=\s*function\s*\(\s*line\s*,\s*col", ed), \
        "gotoLine must accept a column"


def test_synth_frees_its_nodes():
    """WebAudio voices leaked their whole 8-node graph on every note."""
    syn = _read("synth.js")
    assert "disconnect" in syn, "voices never disconnect their nodes"
    assert "dispose" in syn
    assert "_reap" in syn, "voices must be reaped even when the transport is stopped"
    assert "MAX_VOICES" in syn, "polyphony must be bounded"


def test_synth_release_is_a_real_ramp():
    """setTargetAtTime never reaches zero, so osc.stop() clicked."""
    syn = _read("synth.js")
    assert "linearRampToValueAtTime(0.00001" in syn.replace(" ", "") or \
        "linearRampToValueAtTime(0.00001" in syn
    limiter = re.search(r"limiter\.ratio\.value\s*=\s*(\d+)", syn)
    assert limiter and int(limiter.group(1)) >= 12, "the 'limiter' is a mild compressor"


def test_control_curves_track_long_notes():
    """A 200-beat note was reduced to 220 control points."""
    syn = _read("synth.js")
    m = re.search(r"Math\.min\((\d+),\s*Math\.round\(dur \* \d+\)\)", syn)
    assert m and int(m.group(1)) >= 2000, "control-rate cap is too low for long notes"


def test_canvas_area_is_bounded():
    """400 bars x 40 staves must not ask for a canvas the GPU will refuse."""
    app = _read("app.js")
    assert "MAX_CANVAS_PX" in app, "canvas size is unbounded"


def test_bend_display_scale_is_not_hardcoded():
    """A @bend-range of 48 st cannot be drawn on a fixed +/-2 st axis."""
    app = _read("app.js")
    assert "bendRange" in app, "app.js ignores the score's bendRange"
    assert "noteBendScale" in app, "bend curves need a per-note vertical scale"


def test_roll_is_keyboard_operable():
    html = _read("index.html")
    assert 'tabindex="0"' in html, "the piano roll must be focusable"
    assert "aria-live" in html, "selection changes must be announced"
    app = _read("app.js")
    for key in ("ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown"):
        assert key in app, "the roll does not handle " + key


def test_drift_measurement_tool_ships_with_the_repo():
    tool = os.path.join(WEB, "tools", "measure_drift.py")
    assert os.path.isfile(tool), "no reproducible drift measurement exists"
    src = open(tool, encoding="utf-8").read()
    assert "4000" in src, "the tool must measure the 4000-character case"
