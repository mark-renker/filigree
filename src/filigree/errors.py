"""Diagnostics. Owned by the lead agent; import freely, do not edit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class FiligreeError(Exception):
    """Base class for all user-facing Filigree errors."""

    def __init__(self, message: str, line: int = 0, col: int = 0,
                 token: str = "", suggestion: str = "", path: str = "<input>"):
        self.message = message
        self.line = line
        self.col = col
        self.token = token
        self.suggestion = suggestion
        self.path = path
        super().__init__(str(self))

    def __str__(self) -> str:
        head = f"{self.path}:{self.line}:{self.col}: error: {self.message}"
        if self.token:
            head += f"\n  at token: {self.token!r}"
        if self.suggestion:
            head += f"\n  hint: {self.suggestion}"
        return head


class ParseError(FiligreeError):
    pass


class HarmonyError(FiligreeError):
    pass


class GestureError(FiligreeError):
    pass


class RenderError(FiligreeError):
    pass


@dataclass
class Warning_:
    message: str
    line: int = 0
    col: int = 0
    path: str = "<input>"
    kind: str = "general"

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: warning: {self.message}"


def warn(collector: Optional[list], message: str, line: int = 0, col: int = 0,
         path: str = "<input>", kind: str = "general") -> None:
    text = str(Warning_(message, line, col, path, kind))
    if collector is not None:
        collector.append(text)
