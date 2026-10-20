"""Shared pytest configuration.

The repository is a collection of top-level packages (``scoring``,
``sensitivity``, ``api`` and so on) rather than an installed distribution, so
the repository root is added to ``sys.path`` to make those packages
importable from the tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
