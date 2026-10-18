"""
One-shot API discovery for NextChamp.

Runs only GET requests — nothing is created, modified, or deleted.
Paste the full output back so we can design against real endpoints
instead of guesses.

Usage:
    python scripts/discover_api.py
"""

import json
import sys
from typing import Any

import httpx

BASE = "https://api.nextchampion.app"
TIMEOUT = 15.0

# ── 1. Common OpenAPI/Swagger discovery paths ────────────────────
SPEC_PATHS = [
    "/openapi.json",
    "/openapi.yaml",
    "/swagger.json",
    "/swagger/v1/swagger.json",
    "/docs-json",
    "/docs/openapi.json",
    "/docs/swagger.json",
    "/api-json",
    "/api/openapi.json",
    "/api/docs-json",
    "/v1/docs-json",
    "/api/docs",
    "/docs",
    "/swagger",
    "/api",
]

# ── 2. Hypothesized endpoints we need for the expanded bot ───────
#    Format: (path, description)
PROBE_PATHS = [
    # Users
    ("/v1/users", "list users"),
    ("/v1/users/me", "current user (needs auth)"),
    ("/v1/users/by-telegram/0", "user lookup by telegram ID"),
    ("/v1/users/telegram/0", "user lookup by telegram ID (alt)"),
    ("/v1/users/me/notifications", "per-user notifications"),

    # Notifications
    ("/v1/notifications", "global notification feed"),
    ("/v1/notifications?since=2020-01-01T00:00:00Z", "global feed with since filter"),

    # Matches (we know these exist)
    ("/v1/matches", "public matches list (confirmed)"),
    ("/v1/matches/count", "match count (if exists)"),

    # Games
    ("/v1/games", "list of games"),
    ("/v1/games?activeOnly=true", "active games only"),

    # Auth
    ("/v1/auth/me", "current session user"),
    ("/v1/auth/session", "session info"),

    # Admin (may require auth — that's fine, we just note the status)
    ("/v1/admin/users", "admin: list users"),
    ("/v1/admin/stats", "admin: stats"),
    ("/v1/admin/notifications", "admin: notification feed"),

    # Health
    ("/health", "health check"),
    ("/v1/health", "v1 health check"),
]


def _try_get(client: httpx.Client, path: str) -> tuple[int, Any]:
    """Returns (status_code, body_or_error_marker). Never raises."""
    try:
        r = client.get(path)
        ct = r.headers.get("content-type", "")
        if "json" in ct:
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, r.text[:500]
        return r.status_code, r.text[:500]
    except httpx.RequestError as e:
        return -1, f"<network error: {type(e).__name__}: {e}>"


def find_spec(client: httpx.Client) -> dict | None:
    print("=" * 72)
    print("SECTION 1 — OpenAPI / Swagger spec discovery")
    print("=" * 72)
    for path in SPEC_PATHS:
        status, body = _try_get(client, path)
        marker = "✅" if status == 200 else "  "
        print(f"{marker} GET {path:<35} → {status}")

        if status == 200 and isinstance(body, dict):
            # Looks like an OpenAPI spec?
            if "paths" in body or "openapi" in body or "swagger" in body:
                print(f"\n>>> FOUND SPEC at {path}")
                return body

    print("\n(no OpenAPI spec found — falling back to probing)")
    return None


def summarize_spec(spec: dict) -> None:
    print()
    print("=" * 72)
    print("SECTION 2 — Endpoints from the OpenAPI spec")
    print("=" * 72)

    info = spec.get("info") or {}
    print(f"Title:   {info.get('title', '?')}")
    print(f"Version: {info.get('version', '?')}")
    print()

    servers = spec.get("servers") or []
    if servers:
        print("Servers:")
        for s in servers:
            print(f"  - {s.get('url', '?')}")
        print()

    paths = spec.get("paths") or {}
    if not paths:
        print("(no paths in spec)")
        return

    print(f"{len(paths)} path(s) defined:\n")
    for path in sorted(paths.keys()):
        methods = paths[path]
        for method in sorted(methods.keys()):
            op = methods[method]
            summary = op.get("summary") or op.get("operationId") or ""
            # Method + path + summary + security
            security = "🔒" if op.get("security") else "  "
            print(f"  {security} {method.upper():<6} {path:<55} {summary}")


def probe_endpoints(client: httpx.Client) -> None:
    print()
    print("=" * 72)
    print("SECTION 3 — Probing hypothesized endpoints")
    print("=" * 72)
    print("(GET only. 401/403 means the route exists but needs auth — good sign.)\n")

    for path, desc in PROBE_PATHS:
        status, body = _try_get(client, path)

        if status == 200:
            summary = "✅ 200"
            if isinstance(body, list):
                summary += f"  →  list with {len(body)} item(s)"
                if body and isinstance(body[0], dict):
                    keys = list(body[0].keys())[:8]
                    summary += f"  · keys: {keys}"
            elif isinstance(body, dict):
                keys = list(body.keys())[:8]
                summary += f"  →  object with keys: {keys}"
            elif isinstance(body, str):
                summary += f"  →  text: {body[:60]!r}"
            print(f"  {summary:<70} {path}")
            print(f"      ({desc})")

        elif status in (401, 403):
            print(f"  🔒 {status:<4} (auth required — route exists)              {path}")
            print(f"      ({desc})")

        elif status == 404:
            print(f"     {status:<4} (not found)                                 {path}")

        elif status == -1:
            print(f"     ERR   {str(body)[:60]:<60} {path}")

        else:
            print(f"  ⚠️  {status:<4}                                          {path}")
            print(f"      ({desc})")


def main() -> int:
    print()
    print(f"NextChamp API discovery — base: {BASE}")
    print(f"Timeout: {TIMEOUT}s per request")
    print()

    with httpx.Client(base_url=BASE, timeout=TIMEOUT) as client:
        spec = find_spec(client)
        if spec:
            summarize_spec(spec)
        probe_endpoints(client)

    print()
    print("=" * 72)
    print("Done. Paste Sections 1–3 back into the chat.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())