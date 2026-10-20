"""Canonical environment loading for the whole platform.

Every part of the project — the API, the scoring jobs and the ingestion
jobs — reads its configuration from the environment.  Previously each of
them loaded the environment file itself, and they all looked for ``.env``
in the current working directory, while the project's environment file is
``.env.local`` in the repository root.  The result was that the jobs ran
with no configuration at all and failed with confusing errors.

This module is the single place that knows where the environment file
lives and in what order it is applied:

1. ``.env.local`` in the repository root, then
2. ``.env`` in the repository root.

Values that are already present in the process environment always win, so
a deployment's own configuration takes precedence over a file.  This is
what allows the same code to run locally from a file and in production
from the platform's environment variables.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

#: The repository root, derived from this file's location.
REPOSITORY_ROOT = Path(__file__).resolve().parent

#: The environment files, in the order they are applied.
ENVIRONMENT_FILES = (".env.local", ".env")

_loaded_path: Optional[Path] = None
_load_attempted = False


def load_environment() -> Optional[Path]:
    """Load the environment file from the repository root.

    The call is idempotent: the file is read once and the path is
    remembered, so every caller sees the same answer.

    Returns:
        The path that was loaded, or ``None`` when no file was found or
        ``python-dotenv`` is not installed.
    """

    global _loaded_path, _load_attempted

    if _load_attempted:
        return _loaded_path
    _load_attempted = True

    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional dependency
        return None

    for name in ENVIRONMENT_FILES:
        candidate = REPOSITORY_ROOT / name
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            _loaded_path = candidate
            break

    return _loaded_path


def server_key() -> str:
    """Return the server-side Supabase credential.

    The service-role key is preferred: the analytical tables have row
    level security enabled and are only writable by the service role.
    The project's ``SUPABASE_KEY`` holds the *anon* key, so it is only a
    fallback.
    """

    for name in (
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_KEY",
        "SUPABASE_ANON_KEY",
    ):
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return ""


def require_configuration(*names: str) -> None:
    """Raise a clear error when a required variable is missing.

    The message names the variables, so an operator knows exactly what to
    set rather than seeing a connection failure further downstream.
    """

    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing required configuration: "
            + ", ".join(missing)
            + ". Set them in "
            + str(REPOSITORY_ROOT / ENVIRONMENT_FILES[0])
            + " or in the environment."
        )


def ensure_repository_on_path() -> None:
    """Make the repository root importable.

    The ingestion jobs are started as ``python -m ingestion.<module>``,
    which puts the root on the path.  A job that is started as a plain
    script does not, so the root is added explicitly.
    """

    root = str(REPOSITORY_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


__all__ = [
    "ENVIRONMENT_FILES",
    "REPOSITORY_ROOT",
    "ensure_repository_on_path",
    "load_environment",
    "require_configuration",
    "server_key",
]
