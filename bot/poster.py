import logging
from datetime import datetime, timezone

from aiogram.types import FSInputFile, LinkPreviewOptions

from . import media
from .config import settings
from .messages import build_challenge_caption, snapshot_of
from .telegram_bot import bot, open_keyboard
from .types import Match, TrackedMatch

log = logging.getLogger(__name__)


async def post_challenge(match: Match) -> TrackedMatch | None:
    caption = build_challenge_caption(match)
    keyboard = open_keyboard(match.id)

    game_slug = match.game.slug if match.game else None
    image_path = media.resolve(game_slug)

    try:
        if image_path is not None:
            msg = await bot.send_photo(
                chat_id=settings.channel_id,
                photo=FSInputFile(str(image_path)),
                caption=caption,
                reply_markup=keyboard,
            )
            had_photo = True
        else:
            msg = await bot.send_message(
                chat_id=settings.channel_id,
                text=caption,
                reply_markup=keyboard,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
            had_photo = False
    except Exception as e:
        log.error("failed to post match %s: %s", match.id, e)
        return None

    return TrackedMatch(
        message_id=msg.message_id,
        had_photo=had_photo,
        status=match.status,
        created_at=match.createdAt,
        posted_at=datetime.now(timezone.utc).isoformat(),
        snapshot=snapshot_of(match),
    )