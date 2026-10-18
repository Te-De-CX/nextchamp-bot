import logging

from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import db
from ..config import settings
from ..keyboards import admin_menu_keyboard, users_list_keyboard
from ..messages import build_admin_menu, build_users_page

log = logging.getLogger(__name__)

USERS_PER_PAGE = 20


def _is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in settings.admin_ids


def register(dp: Dispatcher) -> None:
    @dp.message(Command("admin"), F.chat.type == "private")
    async def on_admin(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id if message.from_user else None):
            return  # silent — don't reveal the command to non-admins
        await state.clear()
        await message.answer(
            build_admin_menu(db.total_users(), db.blocked_count()),
            reply_markup=admin_menu_keyboard(),
        )

    @dp.callback_query(F.data == "admin:menu")
    async def on_menu(cq: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(cq.from_user.id if cq.from_user else None):
            await cq.answer("Not authorized.")
            return
        await state.clear()
        try:
            await cq.message.edit_text(
                build_admin_menu(db.total_users(), db.blocked_count()),
                reply_markup=admin_menu_keyboard(),
            )
        except Exception:
            pass
        await cq.answer()

    @dp.callback_query(F.data.startswith("admin:users:"))
    async def on_users(cq: CallbackQuery) -> None:
        if not _is_admin(cq.from_user.id if cq.from_user else None):
            await cq.answer("Not authorized.")
            return
        try:
            page = int(cq.data.rsplit(":", 1)[-1])
        except (ValueError, IndexError):
            page = 0

        total = db.total_users()
        total_pages = max(1, (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
        page = max(0, min(page, total_pages - 1))

        users = db.recent_users(limit=USERS_PER_PAGE, offset=page * USERS_PER_PAGE)
        text = build_users_page(users, page, total_pages, total)

        try:
            await cq.message.edit_text(
                text,
                reply_markup=users_list_keyboard(page, total_pages),
            )
        except Exception:
            pass
        await cq.answer()

    @dp.callback_query(F.data == "admin:close")
    async def on_close(cq: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(cq.from_user.id if cq.from_user else None):
            await cq.answer()
            return
        await state.clear()
        try:
            await cq.message.delete()
        except Exception:
            pass
        await cq.answer()

    @dp.callback_query(F.data == "admin:noop")
    async def on_noop(cq: CallbackQuery) -> None:
        await cq.answer()