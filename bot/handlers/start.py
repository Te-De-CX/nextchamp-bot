import logging
from pathlib import Path

from aiogram import Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, LinkPreviewOptions, Message

from .. import db
from ..config import settings
from ..keyboards import main_menu_keyboard
from ..messages import build_help_text, build_welcome_caption

log = logging.getLogger(__name__)


async def _send_welcome(message: Message) -> None:
    user = message.from_user
    if user is None:
        return

    first_time = db.upsert_user(user)
    if first_time:
        log.info("new user: %s (@%s)", user.id, user.username or "?")

    caption = build_welcome_caption(user.first_name)
    keyboard = main_menu_keyboard()

    welcome_path = settings.welcome_media_path
    if welcome_path and Path(welcome_path).is_file():
        try:
            await message.answer_photo(
                photo=FSInputFile(welcome_path),
                caption=caption,
                reply_markup=keyboard,
            )
            return
        except Exception as e:
            log.warning("welcome photo failed (%s) — falling back to text", e)

    await message.answer(
        caption,
        reply_markup=keyboard,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


def register(dp: Dispatcher) -> None:
    @dp.message(CommandStart())
    async def on_start(message: Message) -> None:
        await _send_welcome(message)

    @dp.message(Command("menu"))
    async def on_menu(message: Message) -> None:
        await _send_welcome(message)

    @dp.message(Command("help"))
    async def on_help(message: Message) -> None:
        if message.from_user is not None:
            db.upsert_user(message.from_user)
        await message.answer(
            build_help_text(),
            reply_markup=main_menu_keyboard(),
            link_preview_options=LinkPreviewOptions(is_disabled=False),
        )