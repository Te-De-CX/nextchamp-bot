import logging
import httpx

from .config import settings
from .types import Match

log = logging.getLogger(__name__)

_BASE = settings.nextchamp_api_url.rstrip("/")
_client = httpx.AsyncClient(
    # Render free tier cold starts can take 30-60s. 45s gives the
    # first poll after a spin-down a fighting chance, while keeping
    # connect failures snappy so we retry quickly if the host is down.
    timeout=httpx.Timeout(45.0, connect=15.0),
    headers={"accept": "application/json"},
)


def _bot_headers() -> dict[str, str]:
    """Headers for the /v1/notifications/bot/* endpoints."""
    return {"x-bot-secret": settings.bot_secret}


# ──────────────────────────────────────────────────────────────────
# Matches
# ──────────────────────────────────────────────────────────────────

async def list_matches() -> list[Match]:
    """Public match listing. Accepts either a bare array or `{ "data": [...] }`."""
    try:
        r = await _client.get(f"{_BASE}/v1/matches")
        r.raise_for_status()
    except Exception as e:
        # httpx exceptions often have empty str() — log type explicitly.
        log.warning(
            "list_matches failed: %s: %s",
            type(e).__name__,
            e or "(no message)",
        )
        raise

    payload = r.json()

    if isinstance(payload, list):
        return [Match.model_validate(m) for m in payload]
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [Match.model_validate(m) for m in payload["data"]]
    return []


async def get_match(match_id: str) -> Match | None:
    """Single-match lookup. Returns None on any failure (404, network, etc.)."""
    try:
        r = await _client.get(f"{_BASE}/v1/matches/{match_id}")
        r.raise_for_status()
        return Match.model_validate(r.json())
    except Exception as e:
        log.debug(
            "get_match(%s) failed: %s: %s",
            match_id,
            type(e).__name__,
            e or "(no message)",
        )
        return None


# ──────────────────────────────────────────────────────────────────
# Notifications (bot endpoints)
# ──────────────────────────────────────────────────────────────────

async def pending_notifications(limit: int = 50) -> list[dict]:
    """
    Fetch pending personalized notifications for Telegram delivery.

    Response is a bare array of notification objects. Each has:
      id, userId, telegramId (str|None), telegramUsername,
      eventType, title, message, data (dict), status,
      deliveredAt, createdAt, updatedAt
    """
    try:
        r = await _client.get(
            f"{_BASE}/v1/notifications/bot/pending",
            params={"limit": limit},
            headers=_bot_headers(),
        )
        r.raise_for_status()
    except Exception as e:
        log.warning(
            "pending_notifications failed: %s: %s",
            type(e).__name__,
            e or "(no message)",
        )
        raise

    payload = r.json()
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]
    return []


async def ack_notifications(notification_ids: list[str]) -> int:
    """
    Mark notifications as delivered. Returns the count the backend acked.

    The backend accepts: { "notificationIds": ["id1", "id2", ...] }
    """
    if not notification_ids:
        return 0

    try:
        r = await _client.post(
            f"{_BASE}/v1/notifications/bot/ack",
            json={"notificationIds": notification_ids},
            headers=_bot_headers(),
        )
        r.raise_for_status()
    except Exception as e:
        log.warning(
            "ack_notifications failed: %s: %s",
            type(e).__name__,
            e or "(no message)",
        )
        return 0

    payload = r.json()
    try:
        return int(payload.get("count", 0))
    except (TypeError, ValueError):
        return 0


# ──────────────────────────────────────────────────────────────────

async def close() -> None:
    await _client.aclose()