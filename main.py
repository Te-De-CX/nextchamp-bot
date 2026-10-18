import asyncio
import logging
import sys

from aiogram import Dispatcher
from aiogram.types import CallbackQuery

from bot import api, db, media, notifications, state
from bot.config import settings
from bot.handlers import register_all
from bot.handlers.broadcast import resume_running_jobs
from bot.messages import CLOSED_BUTTON_TOAST, CLOSED_CALLBACK_DATA
from bot.poller import run_forever
from bot.telegram_bot import bot


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("nextchamp-bot")

dp = Dispatcher()


@dp.callback_query(lambda cq: cq.data == CLOSED_CALLBACK_DATA)
async def on_closed_button(cq: CallbackQuery) -> None:
    """Answer taps on the greyed-out 'Challenge Closed' button."""
    await cq.answer(CLOSED_BUTTON_TOAST)


async def main() -> None:
    log.info("🚀 NextChamp Telegram Bot starting…")

    media.init()
    db.init()

    state.load()
    log.info(
        "state: last_seen=%s · tracked=%d match(es)",
        state.last_seen() or "(none)",
        state.tracked_count(),
    )
    log.info(
        "users tracked: %d · admins configured: %d",
        db.total_users(),
        len(settings.admin_ids),
    )

    if not settings.bot_secret:
        log.warning(
            "BOT_SECRET is empty — notifications poller will fail with 401. "
            "Add BOT_SECRET to .env and restart."
        )

    me = await bot.get_me()
    log.info("bot: @%s", me.username)

    # Register user-facing handlers (start, admin, broadcast, menu).
    # Must run AFTER the channel callback handler above so command filters win.
    register_all(dp)

    poll_task = asyncio.create_task(
        run_forever(settings.poll_interval_ms),
        name="api-poller",
    )
    log.info("challenge poller: every %dms", settings.poll_interval_ms)

    notif_task = asyncio.create_task(
        notifications.run_forever(10_000),
        name="notif-poller",
    )
    log.info("notification poller: every 10000ms")

    # Resume any broadcast interrupted by a previous shutdown.
    asyncio.create_task(resume_running_jobs(), name="broadcast-resume")

    try:
        await dp.start_polling(bot)
    finally:
        for task in (poll_task, notif_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        state.save()
        await api.close()
        db.close()
        await bot.session.close()
        log.info("shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)