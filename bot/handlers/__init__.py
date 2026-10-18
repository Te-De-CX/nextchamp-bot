import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Dispatcher
from aiogram.types import TelegramObject, User

from .. import db
from . import admin, broadcast, menu, start

log = logging.getLogger(__name__)


class AutoUnblockMiddleware(BaseMiddleware):
    """
    Fires before every message and callback. If the sender is currently
    marked as blocked in our DB, flip them back to unblocked — so any
    sign of life (a /start, a button tap, a plain message) resumes
    notifications for that user.

    Cheap: one indexed UPDATE per incoming event that no-ops when the
    user isn't blocked.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is not None:
            try:
                if db.unblock_user(user.id):
                    log.info("user %s unblocked on incoming activity", user.id)
            except Exception as e:
                log.warning(
                    "unblock check failed for %s: %s: %s",
                    user.id,
                    type(e).__name__,
                    e or "(no message)",
                )
        return await handler(event, data)


def register_all(dp: Dispatcher) -> None:
    """
    Register all user-facing handlers.

    Order matters:
      1. Middleware (auto-unblock) — runs on every update before handlers.
      2. Command handlers (start, help, admin) — highest priority.
      3. FSM-state handlers (broadcast composing) — must run before the
         catch-all so composing doesn't fall through to the nudge.
      4. Catch-all nudge (menu) — LAST, matches anything left over.
    """
    auto_unblock = AutoUnblockMiddleware()
    dp.message.middleware(auto_unblock)
    dp.callback_query.middleware(auto_unblock)

    start.register(dp)
    admin.register(dp)
    broadcast.register(dp)
    menu.register(dp)