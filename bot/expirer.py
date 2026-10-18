import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import LinkPreviewOptions

from .config import settings
from .messages import build_expired_caption
from .telegram_bot import bot, closed_keyboard
from .types import TrackedMatch

log = logging.getLogger(__name__)


async def expire_challenge(tracked: TrackedMatch, final_status: str) -> bool:
    caption = build_expired_caption(tracked.snapshot, final_status)
    keyboard = closed_keyboard()

    try:
        if tracked.had_photo:
            await bot.edit_message_caption(
                chat_id=settings.channel_id,
                message_id=tracked.message_id,
                caption=caption,
                reply_markup=keyboard,
            )
        else:
            await bot.edit_message_text(
                chat_id=settings.channel_id,
                message_id=tracked.message_id,
                text=caption,
                reply_markup=keyboard,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        return True
    except TelegramBadRequest as e:
        # Idempotency: if nothing changed, treat as success.
        if "message is not modified" in str(e).lower():
            return True
        log.error("failed to expire message %s: %s", tracked.message_id, e)
        return False
    except Exception as e:
        log.error("failed to expire message %s: %s", tracked.message_id, e)
        return False