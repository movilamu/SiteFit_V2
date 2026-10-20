"""The scoring engine.

Importing the package loads the project's environment file, so that the
scoring jobs and the API read the same configuration from the same
place.
"""

from __future__ import annotations

try:
    from platform_env import load_environment

    load_environment()
except ImportError:  # pragma: no cover - the package may be vendored
    pass

