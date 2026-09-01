"""Tests that the documentation tells the truth.

The P7 stranger critic's verdict was that the compiler was good and the docs were
untrustworthy: the README's front-page example did not compile, and the README
described a scoreboard and a `>root` target that did not exist. Those are exactly
the defects a test can prevent from coming back, so this file checks the prose
against the implementation:

* every fenced code block in `README.md` and `docs/*.md` that looks like Filigree
  must compile, with zero warnings;
* the front-page example must be byte-identical to `examples/front_page.fil`;
* every `filigree <sub>` command and every `--flag` the README mentions must exist;
* the concision number the README quotes must equal the one the scorer computed
  into `refs/syntax/tasks.md`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "src")
DOCS = [os.path.join(ROOT, "README.md"),
        os.path.join(ROOT, "START_HERE.md")] + [
    os.path.join(ROOT, "docs", f)
    for f in sorted(os.listdir(os.path.join(ROOT, "docs")))
    if f.endswith(".md")
]

ENV = dict(os.environ, PYTHONPATH=SRC)

# A fenced block is Filigree source if it declares a top-level construct.  Blocks
# that only show a lane fragment, a shell command or a JSON payload are not.
FILIGREE_START = re.compile(
    r"^\s*(@(title|tempo|meter|key|grid|seed|voicing|feel|bend-range)\b"
    r"|stave\s+\w+\s*\{|part\s+\w+\s*\{|gesture\s+\w+|voicing\s+\w+)", re.M)


def fenced_blocks(path: str) -> list[tuple[int, str]]:
    out, cur, start, fence = [], None, 0, ""
    for i, line in enumerate(open(path, encoding="utf-8").read().splitlines(), 1):
        if cur is None:
            m = re.match(r"^\s*(```+)(\w*)\s*$", line)
            if m:
                cur, start, fence = [], i, m.group(2)
            continue
        if re.match(r"^\s*```+\s*$", line):
            body = "\n".join(cur)
            if fence in ("", "filigree", "fil", "text") and FILIGREE_START.search(body):
                out.append((start, body))
            cur = None
            continue
        cur.append(line)
    return out


ALL_BLOCKS = [(p, ln, b) for p in DOCS for ln, b in fenced_blocks(p)]


def compile_source(text: str, tmp_path, name="doc.fil") -> subprocess.CompletedProcess:
    path = os.path.join(str(tmp_path), name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")
    return subprocess.run(
        [sys.executable, "-m", "filigree.cli", "explain", path],
        cwd=ROOT, env=ENV, capture_output=True, text=True)


@pytest.mark.parametrize(
    "path,line,body",
    ALL_BLOCKS,
    ids=[f"{os.path.basename(p)}:{ln}" for p, ln, _ in ALL_BLOCKS])
def test_every_documented_example_compiles_without_warnings(path, line, body, tmp_path):
    p = compile_source(body, tmp_path)
    where = f"{os.path.relpath(path, ROOT)}:{line}"
    assert p.returncode == 0, f"{where} does not compile:\n{p.stderr}"
    warns = [w for w in p.stderr.splitlines() if "warning:" in w]
    assert not warns, f"{where} compiles with {len(warns)} warning(s):\n" + "\n".join(warns)


def test_docs_have_examples_to_check():
    assert len(ALL_BLOCKS) >= 5, "no Filigree blocks were found in the docs at all"


def test_front_page_example_is_the_shipped_file():
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    blocks = [b for _, b in fenced_blocks(os.path.join(ROOT, "README.md"))]
    assert blocks, "the README has no Filigree example"
    front = blocks[0].strip()
    shipped = open(os.path.join(ROOT, "examples", "front_page.fil"),
                   encoding="utf-8").read()
    assert front in shipped, (
        "README.md's front-page example is not identical to "
        "examples/front_page.fil; regenerate one from the other")
    assert "examples/front_page.fil" in readme, \
        "the README should name the file its front-page example lives in"


def _cli_invocations(text: str) -> list[str]:
    """Command lines in the docs that actually invoke this project's CLI."""
    out = []
    for line in text.splitlines():
        line = line.strip().lstrip("$ ").strip()
        line = re.sub(r"\s*#.*$", "", line)
        m = re.match(r"^(?:python\s+-m\s+)?filigree(?:\.cli)?\s+(.*)$", line)
        if m:
            out.append(m.group(1))
    return out


def _cli_help() -> tuple[set[str], str]:
    top = subprocess.run([sys.executable, "-m", "filigree.cli", "--help"],
                         cwd=ROOT, env=ENV, capture_output=True, text=True).stdout
    m = re.search(r"\{([a-z,\-]+)\}", top)
    subs = set(m.group(1).split(",")) if m else set()
    all_help = top
    for sub in sorted(subs):
        all_help += subprocess.run(
            [sys.executable, "-m", "filigree.cli", sub, "--help"],
            cwd=ROOT, env=ENV, capture_output=True, text=True).stdout
    return subs, all_help


def test_readme_only_promises_commands_that_exist():
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    subs, _ = _cli_help()
    assert subs, "could not read the CLI's subcommand list"
    seen = 0
    for inv in _cli_invocations(readme):
        word = inv.split()[0]
        if word.startswith("-"):
            continue
        seen += 1
        assert word in subs, f"README documents `filigree {word}`, which does not exist"
    assert seen >= 3, "the README should show at least a few real CLI invocations"


def test_readme_flags_exist():
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    _, all_help = _cli_help()
    for inv in _cli_invocations(readme):
        for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", inv):
            assert flag in all_help, \
                f"README documents `{flag}` in `filigree {inv}`, which no command accepts"


def test_readme_concision_number_matches_the_generated_scoreboard():
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    tasks = open(os.path.join(ROOT, "refs", "syntax", "tasks.md"),
                 encoding="utf-8").read()
    m = re.search(r"Filigree is shorter on (\d+) of (?:the )?(\d+) tasks", tasks)
    assert m, "refs/syntax/tasks.md has no generated concision record"
    wins, total = m.group(1), m.group(2)
    assert re.search(rf"shorter on {wins} of (?:the )?{total}", readme), (
        f"the README's concision claim disagrees with the scoreboard "
        f"({wins} of {total})")


def test_documented_harmonic_targets_all_parse(tmp_path):
    """`>root` was documented but was a hard parse error (P7 defect)."""
    from filigree.parse import parse

    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    targets = set(re.findall(r"`(>[a-z0-9+|-]+)`", readme))
    assert ">root" in targets, "the README no longer documents `>root`"
    for tgt in sorted(targets):
        src = ("stave t {\n  harm | i | IV |\n  notes | 0 - | 2 - |\n"
               f"  bend!range=8st | __{tgt} |\n}}\n")
        doc = parse(src, "t.fil")           # must not raise
        assert doc is not None


# ── leniency reaches the parser (P7 defect) ────────────────────────────────

BROKEN = """@key C minor
stave t {
  harm  | i9 | Hm7 | Zqx9 | {0 3 zz} |
  notes | 0 - | 2 - | 3 - | 0 -      |
  bend  | __ | _Q | __ | __          |
}
"""


def test_strict_mode_rejects_the_broken_sketch():
    from filigree.errors import ParseError
    from filigree.parse import parse

    with pytest.raises(ParseError):
        parse(BROKEN, "broken.fil")


def test_lenient_mode_compiles_the_broken_sketch_and_says_what_it_did():
    from filigree import compile_source

    score = compile_source(BROKEN, "broken.fil", lenient=True)
    assert score.staves and score.staves[0].notes, \
        "--lenient must still produce playable notes"
    text = "\n".join(score.warnings)
    for bad, what in (("Hm7", "chord symbol"), ("Zqx9", "chord symbol"),
                      ("zz", "semitone offset"), ("Q", "curve glyph")):
        assert bad in text, f"--lenient did not report {bad!r}"
        assert what in text, f"--lenient did not explain the {what} problem"
    assert all("--lenient" in w for w in score.warnings if "not a" in w), \
        "downgraded errors should be marked as such"


def test_lenient_sustains_the_previous_chord_for_a_bad_symbol():
    from filigree import compile_source

    score = compile_source(BROKEN, "broken.fil", lenient=True)
    syms = [c.symbol for c in score.staves[0].chords]
    assert syms and syms[0].startswith("i9"), syms
    assert "Hm7" not in syms and "Zqx9" not in syms, \
        "a rejected symbol must not reach the score"


def test_lenient_does_not_hide_structural_errors():
    from filigree.errors import ParseError
    from filigree.parse import parse

    with pytest.raises(ParseError):
        parse("stave t {\n  notes | 0 2 |\n", "unclosed.fil", lenient=True)


def test_cli_lenient_exits_zero_on_the_broken_sketch(tmp_path):
    path = os.path.join(str(tmp_path), "broken.fil")
    open(path, "w").write(BROKEN)
    strict = subprocess.run([sys.executable, "-m", "filigree.cli", "explain", path],
                            cwd=ROOT, env=ENV, capture_output=True, text=True)
    assert strict.returncode != 0, "strict mode should fail"
    lenient = subprocess.run(
        [sys.executable, "-m", "filigree.cli", "explain", "--lenient", path],
        cwd=ROOT, env=ENV, capture_output=True, text=True)
    assert lenient.returncode == 0, lenient.stderr
    assert "warning:" in lenient.stderr
