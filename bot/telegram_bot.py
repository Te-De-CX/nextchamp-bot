from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import settings
from .messages import (
    CLOSED_BUTTON_TEXT,
    CLOSED_CALLBACK_DATA,
    OPEN_BUTTON_TEXT,
)

bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)


def challenge_url(match_id: str) -> str:
    """
    Mini App deep link to the challenge. Opens the Mini App directly
    (not a browser), and delivers `join_<uuid>` to the frontend as
    initDataUnsafe.start_param.
    """
    return (
        f"https://t.me/{settings.bot_username}/{settings.mini_app_short_name}"
        f"?startapp=join_{match_id}"
    )


def open_keyboard(match_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=OPEN_BUTTON_TEXT, url=challenge_url(match_id)),
    ]])


def closed_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=CLOSED_BUTTON_TEXT,
            callback_data=CLOSED_CALLBACK_DATA,
        ),
    ]])