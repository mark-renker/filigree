"""Filigree — a text language for fast ideation of intricate musical expression.

Public API:

    import filigree
    score = filigree.compile_source(open("piece.fil").read(), "piece.fil")
    filigree.write_midi(score, "piece.mid")
"""

from __future__ import annotations

__version__ = "0.1.0"

from .errors import (  # noqa: F401
    FiligreeError,
    GestureError,
    HarmonyError,
    ParseError,
    RenderError,
)
from .ir import Curve, Note, Score, StaveIR  # noqa: F401


def compile_source(src: str, path: str = "<input>", lenient: bool = False):
    """Parse and resolve Filigree source into an ir.Score.

    ``lenient`` downgrades the recoverable token-level errors -- an unrecognised
    chord symbol, an unknown curve glyph, a malformed pitch set -- to warnings in
    both the parser and the resolver, so a half-typed sketch still plays.
    """
    from .parse import parse
    from .resolve import resolve

    doc = parse(src, path, lenient=lenient)
    return resolve(doc, lenient=lenient)


def write_midi(score, path: str, **kwargs) -> None:
    from .mpe import MpeOptions, write_midi as _write

    opts = MpeOptions(
        bend_range=score.bend_range,
        ppq=score.ppq,
        grid_ms=score.grid_ms,
        **kwargs,
    )
    _write(score, path, opts)


__all__ = [
    "__version__",
    "compile_source",
    "write_midi",
    "Score",
    "Note",
    "Curve",
    "StaveIR",
    "FiligreeError",
    "ParseError",
    "HarmonyError",
    "GestureError",
    "RenderError",
]
