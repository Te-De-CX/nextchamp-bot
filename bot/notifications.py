import asyncio
import hashlib
import logging
import time

from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import LinkPreviewOptions

from . import api, db
from .messages import build_notification_button, render_notification
from .telegram_bot import bot

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_MS = 10_000
BATCH_LIMIT = 50

# ← NEW: dedup window. Same (user, eventType, identifier) within this
# window is treated as a duplicate and silently skipped.
_DEDUP_WINDOW_SECONDS = 15 * 60  # 15 minutes

# ← NEW: in-memory dedup cache. Key → last-delivered timestamp.
# Survives until restart, which is fine: the window is 15 min, and
# after a restart the risk is a single duplicate at worst.
_dedup_cache: dict[str, float] = {}


def _classify_forbidden(err: TelegramForbiddenError) -> str:
    """
    Distinguish between the different Telegram Forbidden variants.

    Telegram returns "Forbidden" for several unrelated reasons, and only
    one of them means the user actually blocked the bot. Treating them all
    as "blocked" falsely blacklists users who simply haven't started the
    bot yet — and that mistake persists in the DB forever.

    Returns one of:
      "blocked"       — user blocked the bot (mark in DB, ack)
      "never_started" — user never tapped /start (do NOT mark, ack)
      "deactivated"   — account deleted (do NOT mark, ack)
      "unknown"       — unrecognized Forbidden (do NOT mark, ack)
    """
    msg = str(err).lower()

    if "bot was blocked by the user" in msg:
        return "blocked"

    if "bot can't initiate conversation with a user" in msg:
        return "never_started"

    if "user is deactivated" in msg:
        return "deactivated"

    return "unknown"


# ──────────────────────────────────────────────────────────────────
# Dedup helpers (NEW)
# ──────────────────────────────────────────────────────────────────

def _build_dedup_key(notif: dict, tg_id: int) -> str | None:
    """
    Stable key for deduplication within the window.

    Prefers the natural identifier from the payload (matchId / reference /
    disputeId). Falls back to a content hash for events without one.

    Returns None for events we never want to dedup (BROADCAST — the admin
    may legitimately want to send the same message twice).
    """
    event_type = str(notif.get("eventType") or "").strip()
    data = notif.get("data") or {}

    # Admin broadcasts are intentional. Never dedup them.
    if event_type == "BROADCAST":
        return None

    identifier = (
        data.get("matchId")
        or data.get("reference")
        or data.get("disputeId")
    )
    if identifier:
        return f"{tg_id}:{event_type}:{identifier}"

    # Fallback: content hash. Catches duplicate event types that don't
    # carry a natural identifier.
    content = f"{notif.get('title', '')}|{notif.get('message', '')}"
    h = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
    return f"{tg_id}:{event_type}:{h}"


def _prune_dedup_cache() -> int:
    """Drop entries older than the window. Returns count pruned."""
    if not _dedup_cache:
        return 0
    cutoff = time.time() - _DEDUP_WINDOW_SECONDS
    stale = [k for k, ts in _dedup_cache.items() if ts < cutoff]
    for k in stale:
        del _dedup_cache[k]
    return len(stale)


# ──────────────────────────────────────────────────────────────────

async def _deliver_one(notif: dict) -> tuple[bool, str]:
    """
    Deliver a single notification.

    Returns (should_ack, outcome) where outcome is one of:
      "delivered"      — DM sent successfully
      "duplicate"      — suppressed by dedup cache (NEW)
      "skipped"        — no telegramId (user hasn't linked Telegram)
      "blocked"        — user blocked the bot; marked blocked in DB
      "never_started"  — user never tapped /start (NOT marked as blocked)
      "deactivated"    — user's Telegram account is deleted
      "forbidden"      — unrecognized Forbidden error (not marked)
      "bad_id"         — invalid telegramId; not recoverable
      "api_error"      — Telegram API rejected; retrying won't help
      "retry"          — transient error; should_ack=False, try again next cycle
    """
    notif_id = notif.get("id")
    event_type = notif.get("eventType")

    tg_id_raw = notif.get("telegramId")
    if tg_id_raw is None:
        log.info("[notif] skipped %s (%s) — no telegramId", notif_id, event_type)
        return True, "skipped"

    try:
        tg_id = int(tg_id_raw)
    except (ValueError, TypeError):
        log.warning(
            "[notif] invalid telegramId %r for %s — acking", tg_id_raw, notif_id,
        )
        return True, "bad_id"

    # ← NEW: dedup check before rendering/sending
    dedup_key = _build_dedup_key(notif, tg_id)
    if dedup_key is not None and dedup_key in _dedup_cache:
        log.info(
            "[notif] duplicate %s (%s) → %s — skipping",
            notif_id, event_type, tg_id,
        )
        return True, "duplicate"

    text = render_notification(notif)
    markup = build_notification_button(notif)

    try:
        await bot.send_message(
            chat_id=tg_id,
            text=text,
            reply_markup=markup,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        # Record on success only, so a failed send still retries.
        if dedup_key is not None:
            _dedup_cache[dedup_key] = time.time()
        log.info("[notif] delivered %s (%s) → %s", notif_id, event_type, tg_id)
        return True, "delivered"

    except TelegramForbiddenError as e:
        kind = _classify_forbidden(e)

        # Record the key for every Forbidden variant — retrying won't help.
        if dedup_key is not None:
            _dedup_cache[dedup_key] = time.time()

        if kind == "blocked":
            log.info(
                "[notif] %s blocked the bot (%s, %s) — marking blocked & acking",
                tg_id, notif_id, event_type,
            )
            db.mark_blocked(tg_id)
            return True, "blocked"

        if kind == "never_started":
            log.info(
                "[notif] %s has never started the bot (%s, %s) — acking silently",
                tg_id, notif_id, event_type,
            )
            return True, "never_started"

        if kind == "deactivated":
            log.info(
                "[notif] %s account deactivated (%s, %s) — acking silently",
                tg_id, notif_id, event_type,
            )
            return True, "deactivated"

        log.warning(
            "[notif] unknown Forbidden for %s (%s, %s): %s — acking without marking",
            tg_id, notif_id, event_type, e,
        )
        return True, "forbidden"

    except TelegramAPIError as e:
        # Record the key — retrying an API-rejected message won't help.
        if dedup_key is not None:
            _dedup_cache[dedup_key] = time.time()
        log.warning(
            "[notif] telegram API error for %s → %s: %s: %s",
            notif_id, tg_id, type(e).__name__, e or "(no message)",
        )
        return True, "api_error"

    except Exception as e:
        # Do NOT record the key — we want the next cycle to retry.
        log.warning(
            "[notif] transient error for %s → %s: %s: %s",
            notif_id, tg_id, type(e).__name__, e or "(no message)",
        )
        return False, "retry"


async def poll_once() -> None:
    # ← NEW: prune stale dedup entries once per cycle
    pruned = _prune_dedup_cache()
    if pruned:
        log.debug("[notif] pruned %d stale dedup entries", pruned)

    try:
        notifications = await api.pending_notifications(limit=BATCH_LIMIT)
    except Exception as e:
        log.warning(
            "[notif] fetch failed: %s: %s",
            type(e).__name__,
            e or "(no message)",
        )
        return

    if not notifications:
        return

    ack_ids: list[str] = []
    counts = {
        "delivered": 0,
        "duplicate": 0,
        "skipped": 0,
        "blocked": 0,
        "never_started": 0,
        "deactivated": 0,
        "forbidden": 0,
        "bad_id": 0,
        "api_error": 0,
        "retry": 0,
    }

    for notif in notifications:
        should_ack, outcome = await _deliver_one(notif)
        counts[outcome] = counts.get(outcome, 0) + 1
        if should_ack:
            nid = notif.get("id")
            if nid:
                ack_ids.append(nid)

    acked = 0
    if ack_ids:
        try:
            acked = await api.ack_notifications(ack_ids)
        except Exception as e:
            log.warning(
                "[notif] ack failed: %s: %s",
                type(e).__name__,
                e or "(no message)",
            )

    log.info(
        "[notif] cycle: delivered=%d duplicate=%d skipped=%d blocked=%d "
        "never_started=%d deactivated=%d forbidden=%d bad_id=%d "
        "api_error=%d retry=%d | acked=%d",
        counts["delivered"], counts["duplicate"], counts["skipped"],
        counts["blocked"], counts["never_started"], counts["deactivated"],
        counts["forbidden"], counts["bad_id"], counts["api_error"],
        counts["retry"], acked,
    )


async def run_forever(interval_ms: int = DEFAULT_INTERVAL_MS) -> None:
    """
    Poll for pending notifications on a fixed cadence. The sleep adjusts
    so each full cycle (poll + sleep) is approximately `interval_ms`.
    """
    interval = max(1.0, interval_ms / 1000.0)
    loop = asyncio.get_running_loop()
    log.info(
        "[notif] poller started, interval=%ds, dedup window=%ds",
        int(interval), _DEDUP_WINDOW_SECONDS,
    )

    while True:
        cycle_start = loop.time()
        try:
            await poll_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning(
                "[notif] unhandled error in cycle: %s: %s",
                type(e).__name__,
                e or "(no message)",
            )

        elapsed = loop.time() - cycle_start
        await asyncio.sleep(max(0.1, interval - elapsed))