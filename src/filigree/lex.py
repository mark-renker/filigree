"""Filigree lexer (piece P1).

Two lexical regimes live in one file:

* **generic mode** — directives, ``gesture``/``feel``/``voicing``/``part``/``stave``
  headers and gesture expressions.  Ordinary identifier / number / operator
  tokenisation.
* **lane mode** — the body of a lane line (``notes | 0 . 2 3 | ...``).  Here
  whitespace is *significant*: it separates slots, so the lexer hands the parser
  bar separators plus opaque ``chunk`` tokens (bracket-aware, so ``[0 2]`` and
  ``{ bass: 0 ; mid: 3 }`` survive as single chunks) and ``gap`` tokens for the
  runs of whitespace between them.

A line is lexed in lane mode iff it begins with one of the lane names from
SPEC §3.2 followed by ``!``, ``@``, ``|``, whitespace or end of line.  That set
is closed (``cc<n>`` is the only open-ended member) which keeps the decision
unambiguous — no heuristics.

Public API (fixed by docs/ARCH.md)::

    tokenize(src: str, path: str = "<input>") -> list[Token]
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Token", "tokenize", "LANE_NAMES", "GENERIC_KINDS", "LANE_KINDS"]


@dataclass(frozen=True)
class Token:
    """A lexical token.  ``line``/``col`` are 1-based."""

    kind: str
    text: str
    line: int
    col: int

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return f"{self.kind}({self.text!r})@{self.line}:{self.col}"


# --------------------------------------------------------------------------
# lane recognition
# --------------------------------------------------------------------------

#: Lane names from SPEC §3.2.  ``cc<n>`` is handled by the regex below.
LANE_NAMES: tuple[str, ...] = (
    "harm", "notes", "voices", "bend", "press", "timbre", "amp", "pan",
)

_BLOCK_KW_RE = re.compile(r"(stave|part)\b")

_LANE_RE = re.compile(
    r"(harm|notes|voices|bend|press|timbre|amp|pan|cc\d+)(?=$|[!@|\s])"
)

#: Token kinds produced in generic mode.
GENERIC_KINDS = ("directive", "ident", "number", "string", "op", "punct", "newline")
#: Token kinds produced in lane mode.
LANE_KINDS = ("lane", "laneopt", "lanevoice", "bar", "chunk", "gap")

_TWO_CHAR_OPS = ("->", ">>", "..", "::")
_SINGLE_OPS = set("+-*/@=!?%<>|&")
_PUNCT = set("()[]{},;:.")

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_UNIT_RE = re.compile(r"(st|hz|ms|bpm|beat|cent|%)")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_#-]*")

_OPEN = {"[": "]", "(": ")", "{": "}", "<": ">"}
_CLOSE = {"]": "[", ")": "(", "}": "{", ">": "<"}


# --------------------------------------------------------------------------
# comment stripping
# --------------------------------------------------------------------------

def _strip_comment(line: str) -> str:
    """Remove a trailing ``#`` comment.

    ``#`` only opens a comment when it is at line start or preceded by
    whitespace *and* followed by whitespace / end of line.  That keeps sharps
    (``#4``, ``#iv``, ``F#7``, ``#11``) working, which SPEC §4/§5 require.
    Hashes inside string literals are never comments.
    """
    out: list[str] = []
    in_str = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                out.append(ch)
                out.append(line[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "#":
            before_ok = i == 0 or line[i - 1].isspace()
            after = line[i + 1] if i + 1 < n else ""
            after_ok = after == "" or after.isspace() or after == "#"
            if before_ok and after_ok:
                break
        out.append(ch)
        i += 1
    return "".join(out)


# --------------------------------------------------------------------------
# generic mode
# --------------------------------------------------------------------------

def _atom_end(tok: Token | None) -> bool:
    """True when *tok* can end an atom (so a following ``-`` is binary)."""
    if tok is None:
        return False
    if tok.kind in ("number", "ident", "string"):
        return True
    return tok.kind == "punct" and tok.text in (")", "]", "}")


def _lex_generic(text: str, line: int, out: list[Token]) -> None:
    i = 0
    n = len(text)
    first = True
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        col = i + 1

        # directive: '@name' as the first token of a line
        if ch == "@" and first:
            m = _IDENT_RE.match(text, i + 1)
            if m:
                out.append(Token("directive", text[i:m.end()], line, col))
                i = m.end()
                first = False
                continue

        if ch == '"':
            j = i + 1
            buf: list[str] = []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append({"n": "\n", "t": "\t"}.get(text[j + 1], text[j + 1]))
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            if j >= n:
                # unterminated: emit what we have, parser reports the error
                out.append(Token("badstring", text[i:], line, col))
                return
            out.append(Token("string", "".join(buf), line, col))
            i = j + 1
            first = False
            continue

        two = text[i:i + 2]
        if two in _TWO_CHAR_OPS:
            out.append(Token("op", two, line, col))
            i += 2
            first = False
            continue

        # number, possibly with a leading sign and a unit suffix
        neg = ""
        j = i
        if ch in "+-" and not _atom_end(out[-1] if out else None):
            if j + 1 < n and text[j + 1].isdigit():
                neg = ch
                j += 1
        m = _NUM_RE.match(text, j)
        if m and (neg or ch.isdigit()):
            j = m.end()
            um = _UNIT_RE.match(text, j)
            unit = ""
            if um:
                unit = um.group(0)
                j = um.end()
            out.append(Token("number", neg + m.group(0) + unit, line, col))
            i = j
            first = False
            continue

        m = _IDENT_RE.match(text, i)
        if m:
            out.append(Token("ident", m.group(0), line, col))
            i = m.end()
            first = False
            continue

        if ch in _SINGLE_OPS:
            out.append(Token("op", ch, line, col))
            i += 1
            first = False
            continue
        if ch in _PUNCT:
            out.append(Token("punct", ch, line, col))
            i += 1
            first = False
            continue

        out.append(Token("unknown", ch, line, col))
        i += 1
        first = False


# --------------------------------------------------------------------------
# lane mode
# --------------------------------------------------------------------------

_Chars = list[tuple[str, int, int]]  # (char, line, col)


def _lex_lane(chars: _Chars, out: list[Token]) -> None:
    n = len(chars)
    i = 0

    def txt(a: int, b: int) -> str:
        return "".join(c for c, _l, _c in chars[a:b])

    # --- header: lane name, then !opt=val / @voice ------------------------
    m = _LANE_RE.match(txt(0, n))
    assert m is not None
    name_end = m.end()
    out.append(Token("lane", m.group(0), chars[0][1], chars[0][2]))
    i = name_end

    while i < n:
        ch, ln, co = chars[i]
        if ch == "!":
            # ``!gesture@lead=cry`` keeps the '@voice' inside the option name,
            # while ``!shape=ease@lead`` ends the option at the '@'.
            j = i + 1
            seen_eq = False
            while j < n:
                c = chars[j][0]
                if c in "!| \t":
                    break
                if c == "@" and seen_eq:
                    break
                if c == "=":
                    seen_eq = True
                j += 1
            out.append(Token("laneopt", txt(i + 1, j), ln, co))
            i = j
            continue
        if ch == "@":
            j = i + 1
            while j < n and (chars[j][0].isalnum() or chars[j][0] in "_-"):
                j += 1
            out.append(Token("lanevoice", txt(i + 1, j), ln, co))
            i = j
            continue
        break

    # --- body -------------------------------------------------------------
    stack: list[str] = []
    while i < n:
        ch, ln, co = chars[i]
        if ch.isspace():
            j = i
            while j < n and chars[j][0].isspace():
                j += 1
            out.append(Token("gap", txt(i, j), ln, co))
            i = j
            continue
        if ch == "|" and not stack:
            out.append(Token("bar", "|", ln, co))
            i += 1
            continue
        # a chunk: consume until whitespace or a depth-0 '|'
        start = i
        while i < n:
            c = chars[i][0]
            if c.isspace() and not stack:
                break
            if c == "|" and not stack:
                # ">|" is the "next note in this lane" target (SPEC §7)
                if i > start and chars[i - 1][0] == ">":
                    i += 1
                    continue
                break
            if c in _OPEN:
                stack.append(c)
            elif c in _CLOSE:
                want = _CLOSE[c]
                if stack and stack[-1] == want:
                    stack.pop()
                elif c == ">":
                    pass  # a '>' harmonic target, not an alternation close
                else:
                    stack.clear()
            i += 1
        out.append(Token("chunk", txt(start, i), chars[start][1], chars[start][2]))

    out.append(Token("newline", "\n", chars[-1][1], chars[-1][2] + 1))


def _inline_block_split(stripped: str) -> tuple[str, str, int] | None:
    """Split ``stave a { notes | 0 | }`` into header / lane body.

    Returns ``(head_including_brace, tail, tail_offset)`` or None when the line
    is not a one-line block whose body starts with a lane name.
    """
    if not _BLOCK_KW_RE.match(stripped):
        return None
    idx = stripped.find("{")
    if idx == -1:
        return None
    j = idx + 1
    while j < len(stripped) and stripped[j] in " \t":
        j += 1
    if j >= len(stripped) or not _LANE_RE.match(stripped[j:]):
        return None
    return stripped[:idx + 1], stripped[j:], j


def _lane_depth_delta(text: str) -> int:
    """Net bracket depth of *text* (used to join continuation lines)."""
    depth = 0
    in_str = False
    for c in text:
        if c == '"':
            in_str = not in_str
        elif in_str:
            continue
        elif c in "[({":
            depth += 1
        elif c in "])}":
            depth -= 1
    return depth


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def tokenize(src: str, path: str = "<input>") -> list[Token]:
    """Tokenise Filigree source.

    Returns a flat list of :class:`Token`.  ``path`` is accepted for signature
    compatibility (the parser owns diagnostics) and is not otherwise used.
    """
    out: list[Token] = []
    lines = src.split("\n")
    i = 0
    total = len(lines)
    while i < total:
        raw = lines[i]
        code = _strip_comment(raw)
        if not code.strip():
            i += 1
            continue
        stripped = code.lstrip()
        offset = len(code) - len(stripped)

        # A one-line block such as ``stave a { notes | 0 | }`` — lex the header
        # up to '{' generically, then the remainder as a lane line, then the
        # trailing '}'.
        brace = _inline_block_split(stripped)
        if brace is not None:
            head, tail, tail_off = brace
            _lex_generic(code[:offset + len(head)], i + 1, out)
            out.append(Token("newline", "\n", i + 1, offset + len(head) + 1))
            stripped = tail
            offset += tail_off

        closers = 0
        if _LANE_RE.match(stripped):
            body = stripped.rstrip()
            while _lane_depth_delta(body) < 0 and body.endswith("}"):
                body = body[:-1].rstrip()
                closers += 1
            stripped = body

        if _LANE_RE.match(stripped):
            # join continuation lines while brackets are open (the multi-line
            # ``voices | { ... }`` form of SPEC §6)
            chars: _Chars = [
                (c, i + 1, offset + k + 1) for k, c in enumerate(stripped)
            ]
            depth = _lane_depth_delta(stripped)
            j = i
            while depth > 0 and j + 1 < total:
                j += 1
                nxt = _strip_comment(lines[j])
                chars.append((" ", j + 1, 1))
                chars.extend((c, j + 1, k + 1) for k, c in enumerate(nxt))
                depth += _lane_depth_delta(nxt)
            # trim trailing whitespace chars
            while chars and chars[-1][0].isspace():
                chars.pop()
            if chars:
                _lex_lane(chars, out)
            for k in range(closers):
                out.append(Token("punct", "}", j + 1,
                                 offset + len(stripped) + 1 + k))
                out.append(Token("newline", "\n", j + 1,
                                 offset + len(stripped) + 2 + k))
            i = j + 1
            continue
        _lex_generic(code, i + 1, out)
        out.append(Token("newline", "\n", i + 1, len(code) + 1))
        i += 1
    out.append(Token("eof", "", total, 1))
    return out
