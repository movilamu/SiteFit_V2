"""Obtain a real Supabase access token for an operational test account.

The account is created with the service-role (admin) key, which is the
only way to create a user without a browser.  The password is generated
and printed once so the operator can sign in through the normal Google
flow afterwards; the account can also be deleted with ``--delete``.

This is a *test* account for the deployment the operator is auditing, not
a mock: the token it produces is a genuine Supabase JWT that the API
verifies against the project's signing key.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_env import load_environment, server_key  # noqa: E402

load_environment()

import os  # noqa: E402

import requests  # noqa: E402

EMAIL_DOMAIN = "example.com"


def _admin_headers() -> dict:
    key = server_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def create_user(email: str, password: str) -> dict:
    response = requests.post(
        f"{os.environ['SUPABASE_URL']}/auth/v1/admin/users",
        headers=_admin_headers(),
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": "Operational Audit"},
        },
        timeout=60,
    )
    if response.status_code not in (200, 201):
        raise SystemExit(
            f"Could not create the user ({response.status_code}): {response.text[:400]}"
        )
    return response.json()


def sign_in(email: str, password: str) -> dict:
    response = requests.post(
        f"{os.environ['SUPABASE_URL']}/auth/v1/token?grant_type=password",
        headers=_admin_headers(),
        json={"email": email, "password": password},
        timeout=60,
    )
    if response.status_code != 200:
        raise SystemExit(
            f"Could not sign in ({response.status_code}): {response.text[:400]}"
        )
    return response.json()


def delete_user(user_id: str) -> None:
    response = requests.delete(
        f"{os.environ['SUPABASE_URL']}/auth/v1/admin/users/{user_id}",
        headers=_admin_headers(),
        timeout=60,
    )
    print(f"delete: HTTP {response.status_code}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--delete", metavar="USER_ID", default=None)
    parser.add_argument("--token-only", action="store_true")
    args = parser.parse_args()

    if args.delete:
        delete_user(args.delete)
        return 0

    email = args.email or f"audit-{secrets.token_hex(4)}@{EMAIL_DOMAIN}"
    password = args.password or secrets.token_urlsafe(16)

    created = create_user(email, password)
    user_id = created.get("id")
    session = sign_in(email, password)

    access_token = session.get("access_token")
    if not access_token:
        raise SystemExit("The sign-in did not return an access token.")

    if args.token_only:
        print(access_token)
        return 0

    print(f"email    : {email}")
    print(f"password : {password}")
    print(f"user_id  : {user_id}")
    print(f"token    : {access_token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
