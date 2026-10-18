import asyncio
import logging
from datetime import datetime, timezone

from . import api, state
from .expirer import expire_challenge
from .poster import post_challenge
from .types import Match

log = logging.getLogger(__name__)


def _newest_created_at(matches: list[Match]) -> str | None:
    newest: str | None = None
    for m in matches:
        if newest is None or m.createdAt > newest:
            newest = m.createdAt
    return newest


async def poll_once() -> None:
    try:
        all_matches = await api.list_matches()
    except Exception as e:
        # httpx exceptions often have empty str() — log the type explicitly.
        # Downgraded to WARNING because Render free-tier cold starts
        # routinely produce a few timeouts before the API warms up.
        log.warning(
            "poll failed: %s: %s",
            type(e).__name__,
            e or "(no message)",
        )
        return

    open_matches = [m for m in all_matches if m.status == "OPEN"]
    open_ids = {m.id for m in open_matches}

    # ── 1. Discovery ──────────────────────────────────────────
    last_seen = state.last_seen()

    if last_seen is None:
        # First-ever run: record a baseline, do NOT backfill.
        baseline = _newest_created_at(open_matches) or datetime.now(timezone.utc).isoformat()
        state.set_last_seen(baseline)
        log.info("baseline set to %s — existing challenges will not be posted", baseline)
    else:
        fresh = sorted(
            (m for m in open_matches if m.createdAt > last_seen),
            key=lambda m: m.createdAt,
        )
        for match in fresh:
            entry = await post_challenge(match)
            if entry is not None:
                state.track(match.id, entry)
                log.info(
                    "✔ posted %s · %s",
                    match.id,
                    match.game.name if match.game else "unknown game",
                )
            else:
                log.warning("failed to post %s — advancing cursor anyway", match.id)
            # Advance cursor whether post succeeded or not, so a broken
            # match doesn't block the queue forever.
            state.set_last_seen(match.createdAt)

    # ── 2. Expiry ─────────────────────────────────────────────
    for match_id, tracked in state.tracked_items():
        if tracked.status != "OPEN":
            continue
        if match_id in open_ids:
            continue

        # It's gone from the OPEN list — fetch definitive status.
        fresh = await api.get_match(match_id)
        final_status = fresh.status if fresh else "CANCELLED"

        if final_status == "OPEN":
            continue  # transient blip; leave it alone

        if await expire_challenge(tracked, final_status):
            state.update_status(match_id, final_status)
            log.info("⌛ expired %s → %s", match_id, final_status)


async def run_forever(interval_ms: int) -> None:
    """
    Poll on a fixed cadence: each full cycle (poll + sleep) takes
    approximately `interval_ms`, rather than `poll_duration + interval_ms`.

    This keeps detection latency stable even when the API is slow.
    """
    interval = max(1.0, interval_ms / 1000.0)
    loop = asyncio.get_running_loop()  # ← FIX: get_running_loop, not get_event_loop

    while True:
        cycle_start = loop.time()
        try:
            await poll_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning(
                "unhandled error in poll cycle: %s: %s",
                type(e).__name__,
                e or "(no message)",
            )

        elapsed = loop.time() - cycle_start
        sleep_for = max(0.1, interval - elapsed)
        await asyncio.sleep(sleep_for)