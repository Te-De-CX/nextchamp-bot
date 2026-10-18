import logging

from aiogram import Dispatcher, F
from aiogram.types import Message

from .. import db
from ..keyboards import main_menu_keyboard

log = logging.getLogger(__name__)


def register(dp: Dispatcher) -> None:
    # Catch-all for text messages in private chats that aren't commands.
    # Updates last_seen, then nudges back to the menu.
    @dp.message(F.chat.type == "private", ~F.text.startswith("/"))
    async def on_any_message(message: Message) -> None:
        if message.from_user is not None:
            db.upsert_user(message.from_user)

        await message.answer(
            "Tap one of the buttons below 👇 or use /help.",
            reply_markup=main_menu_keyboard(),
        )