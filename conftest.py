"""Repo-level pytest bootstrap.

Puts ``src/`` (so ``import filigree`` works from a checkout without an install)
and the repo root (so ``import tools.audit_mpe`` works) on ``sys.path``.  This
is idempotent and harmless after ``pip install -e .``.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, "src")
_TOOLS = os.path.join(_ROOT, "tools")

for _p in (_SRC, _ROOT, _TOOLS):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)


def pytest_report_header(config):  # pragma: no cover - informational
    return f"filigree: src={_SRC}"
