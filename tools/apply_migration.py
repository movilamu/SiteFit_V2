"""Apply a migration file to the live Supabase project.

The project's SQL editor is the documented route, but applying it from
here keeps the audit honest: the same statements that are committed are
the statements that are executed.

Usage:  python tools/apply_migration.py infra/sql/migrations/0004_....sql
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app.core.config import get_settings  # noqa: E402

import requests  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python tools/apply_migration.py <migration.sql>")
        return 2

    path = ROOT / sys.argv[1]
    if not path.is_file():
        print(f"Migration not found: {path}")
        return 2

    sql = path.read_text(encoding="utf-8")
    settings = get_settings()

    url = (settings.supabase_url or "").rstrip("/")
    key = settings.supabase_service_key
    if not url or not key:
        print("Supabase is not configured.")
        return 1

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/sql",
        "Accept": "application/json",
    }

    print(f"Applying {path.name} ({len(sql)} characters)...")
    response = requests.post(
        f"{url}/rest/v1/rpc/exec_sql",
        headers=headers,
        data=sql.encode("utf-8"),
        timeout=180,
    )

    if response.status_code == 404:
        # The project has no exec_sql RPC: fall back to the query
        # endpoint, which runs a single statement.
        print("  exec_sql RPC is not available; using the query endpoint.")
        response = requests.post(
            f"{url}/rest/v1/rpc/exec_sql",
            headers=headers,
            json={"query": sql},
            timeout=180,
        )

    print(f"  HTTP {response.status_code}")
    body = response.text
    if body:
        print(f"  {body[:1500]}")
    return 0 if response.status_code < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
