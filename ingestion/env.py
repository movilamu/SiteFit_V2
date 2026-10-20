"""Shared environment loading for the ingestion jobs.

The implementation lives in :mod:`platform_env`, at the repository root,
so that the API, the scoring jobs and the ingestion jobs all resolve the
environment file in exactly the same way.
"""

from __future__ import annotations

from platform_env import (  # noqa: F401  (re-exported for the ingestion jobs)
    ENVIRONMENT_FILES,
    REPOSITORY_ROOT,
    ensure_repository_on_path,
    load_environment,
    require_configuration,
    server_key,
)

__all__ = [
    "ENVIRONMENT_FILES",
    "REPOSITORY_ROOT",
    "ensure_repository_on_path",
    "load_environment",
    "require_configuration",
    "server_key",
]
