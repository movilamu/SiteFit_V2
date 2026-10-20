"""Audit every backend endpoint against the running API.

For each endpoint the audit records:

* the authentication requirement implied by the route,
* the response with no token, with an invalid token, and with a real
  Supabase token,
* the response to a deliberately malformed request, where the endpoint
  accepts a body.

The output is a table that can be pasted into the final report.  The
token is read from the environment so it is never written to disk.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_env import load_environment  # noqa: E402

load_environment()

BASE = os.getenv("API_AUDIT_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# A body that every mutating endpoint can be given to see how it
# validates.  It is deliberately wrong: the point is to observe the
# validation path, not to make the request succeed.
MALFORMED_BODY: dict[str, Any] = {
    "name": 12345,
    "weights": "not-a-mapping",
    "method": "not-a-method",
    "site_id": ["not", "a", "string"],
    "description": {"unexpected": "type"},
}


def _status(response: requests.Response) -> str:
    return f"{response.status_code}"


def _detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:120].replace("\n", " ")
    if isinstance(payload, dict):
        detail = payload.get("detail", payload.get("message"))
        if isinstance(detail, list):
            detail = "; ".join(
                f"{item.get('loc')}: {item.get('msg')}" for item in detail[:3]
            )
        return str(detail)[:140].replace("\n", " ")
    return str(payload)[:140].replace("\n", " ")


def audit(token: str | None) -> list[dict[str, Any]]:
    schema = requests.get(f"{BASE}/openapi.json", timeout=60).json()
    results: list[dict[str, Any]] = []

    headers_ok = {"Accept": "application/json"}
    headers_auth = {**headers_ok, "Authorization": f"Bearer {token}"}

    for path, operations in sorted(schema.get("paths", {}).items()):
        for method, operation in operations.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue

            row: dict[str, Any] = {
                "endpoint": f"{method.upper()} {path}",
                "summary": (operation.get("summary") or "")[:60],
                "no_token": "-",
                "bad_token": "-",
                "with_token": "-",
                "malformed": "-",
                "notes": "",
            }

            # 1. No token.
            try:
                response = requests.request(
                    method.upper(), f"{BASE}{path}", headers=headers_ok, timeout=60
                )
                row["no_token"] = _status(response)
                if response.status_code not in (200, 401, 403, 405, 422, 501):
                    row["notes"] = _detail(response)
            except requests.RequestException as exc:
                row["no_token"] = f"ERR {type(exc).__name__}"

            # 2. An invalid token.
            try:
                response = requests.request(
                    method.upper(),
                    f"{BASE}{path}",
                    headers={**headers_ok, "Authorization": "Bearer not-a-real-token"},
                    timeout=60,
                )
                row["bad_token"] = _status(response)
                if response.status_code not in (401, 403):
                    row["notes"] = (
                        f"{row['notes']} | invalid token was accepted"
                    ).strip(" |")
            except requests.RequestException as exc:
                row["bad_token"] = f"ERR {type(exc).__name__}"

            # 3. A real token.
            try:
                response = requests.request(
                    method.upper(),
                    f"{BASE}{path}",
                    headers=headers_auth,
                    timeout=120,
                )
                row["with_token"] = _status(response)
                if response.status_code >= 400 and not row["notes"]:
                    row["notes"] = _detail(response)
            except requests.RequestException as exc:
                row["with_token"] = f"ERR {type(exc).__name__}"

            # 4. A malformed body.
            if method.upper() in {"POST", "PUT", "PATCH"}:
                try:
                    response = requests.request(
                        method.upper(),
                        f"{BASE}{path}",
                        headers={**headers_auth, "Content-Type": "application/json"},
                        data=json.dumps(MALFORMED_BODY),
                        timeout=60,
                    )
                    row["malformed"] = _status(response)
                    if response.status_code >= 500:
                        row["notes"] = (
                            f"{row['notes']} | malformed body caused a server error"
                        ).strip(" |")
                except requests.RequestException as exc:
                    row["malformed"] = f"ERR {type(exc).__name__}"

            results.append(row)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", default=os.getenv("API_AUDIT_TOKEN"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.token:
        print("A token is required: set API_AUDIT_TOKEN.")
        return 2

    started = time.time()
    rows = audit(args.token)
    elapsed = time.time() - started

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    header = (
        f"{'Endpoint':46s} {'no-tok':>7s} {'bad-tok':>8s} "
        f"{'auth':>6s} {'malformed':>10s}  Notes"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['endpoint'][:45]:46s} {row['no_token']:>7s} {row['bad_token']:>8s} "
            f"{row['with_token']:>6s} {row['malformed']:>10s}  {row['notes'][:70]}"
        )
    print()
    print(f"{len(rows)} endpoint(s) audited in {elapsed:.1f}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
