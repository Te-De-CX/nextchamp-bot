import asyncio
import json
import logging
import re

from aiogram import Dispatcher, F
from aiogram.exceptions import TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .. import db
from ..config import settings
from ..keyboards import (
    broadcast_audience_keyboard,
    broadcast_confirm_keyboard,
)
from ..messages import (
    build_broadcast_cancel_text,
    build_broadcast_compose_prompt,
    build_broadcast_confirm,
    build_broadcast_final_report,
    build_broadcast_preview_text,
    build_broadcast_progress,
)
from ..telegram_bot import bot

log = logging.getLogger(__name__)

BUTTON_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)\s*$", re.MULTILINE)
PROGRESS_UPDATE_EVERY = 50
SEND_DELAY = 0.05  # ~20 msgs/sec, safely under Telegram's 30/sec cap


class BroadcastFlow(StatesGroup):
    composing = State()


def _is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in settings.admin_ids


# ──────────────────────────────────────────────────────────────────
# Parsing & serialization
# ──────────────────────────────────────────────────────────────────

def _parse_button(text: str) -> tuple[str, dict | None]:
    """Extract trailing [Label](url). Returns (cleaned_text, button_or_None)."""
    m = BUTTON_RE.search(text)
    if not m:
        return text, None
    label = m.group(1).strip()
    url = m.group(2).strip()
    if not label or not url.startswith(("http://", "https://", "tg://")):
        return text, None
    return text[: m.start()].rstrip(), {"label": label, "url": url}


def _serialize_message(message: Message) -> dict | None:
    if message.photo:
        clean, button = _parse_button(message.caption or "")
        return {
            "kind": "photo",
            "file_id": message.photo[-1].file_id,
            "text": clean,
            "button": button,
        }
    if message.text:
        clean, button = _parse_button(message.text)
        return {
            "kind": "text",
            "text": clean,
            "button": button,
        }
    return None


def _build_markup(payload: dict) -> InlineKeyboardMarkup | None:
    b = payload.get("button")
    if not b:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=b["label"], url=b["url"]),
    ]])


# ──────────────────────────────────────────────────────────────────
# Sending
# ──────────────────────────────────────────────────────────────────

async def _send_one(telegram_id: int, payload: dict) -> tuple[bool, bool]:
    """Returns (delivered, was_blocked)."""
    try:
        markup = _build_markup(payload)
        if payload["kind"] == "photo":
            await bot.send_photo(
                chat_id=telegram_id,
                photo=payload["file_id"],
                caption=payload.get("text") or None,
                reply_markup=markup,
            )
        else:
            await bot.send_message(
                chat_id=telegram_id,
                text=payload["text"],
                reply_markup=markup,
            )
        return True, False
    except TelegramForbiddenError:
        return False, True
    except Exception as e:
        log.warning(
            "broadcast send to %s failed: %s: %s",
            telegram_id,
            type(e).__name__,
            e or "(no message)",
        )
        return False, False


async def _run_broadcast(job_id: int, admin_id: int) -> None:
    job = next((j for j in db.get_running_jobs() if j["id"] == job_id), None)
    if job is None:
        log.warning("broadcast job %s not found (already done?)", job_id)
        return

    payload = json.loads(job["payload_json"])
    audience = job["audience"]
    cursor = int(job["progress_cursor"])
    sent = int(job["sent"])
    blocked = int(job["blocked"])
    failed = int(job["failed"])
    total = int(job["total"])

    progress_msg = None
    try:
        progress_msg = await bot.send_message(
            chat_id=admin_id,
            text=build_broadcast_progress(
                audience, sent + blocked + failed, total, sent, blocked, failed,
            ),
        )
    except Exception:
        pass

    since_last_update = 0

    while True:
        batch = db.get_broadcast_batch(audience, cursor, limit=20)
        if not batch:
            break

        for user in batch:
            delivered, was_blocked = await _send_one(user["telegram_id"], payload)
            if delivered:
                sent += 1
            elif was_blocked:
                blocked += 1
                db.mark_blocked(user["telegram_id"])
            else:
                failed += 1
            cursor = user["telegram_id"]

            # Persist cursor after every send — a crash loses at most 1 user.
            db.update_broadcast_progress(job_id, cursor, sent, blocked, failed)

            since_last_update += 1
            await asyncio.sleep(SEND_DELAY)

        if progress_msg and since_last_update >= PROGRESS_UPDATE_EVERY:
            since_last_update = 0
            try:
                await bot.edit_message_text(
                    chat_id=admin_id,
                    message_id=progress_msg.message_id,
                    text=build_broadcast_progress(
                        audience,
                        sent + blocked + failed,
                        total,
                        sent,
                        blocked,
                        failed,
                    ),
                )
            except Exception:
                pass

    db.finish_broadcast_job(job_id, status="done")

    if progress_msg:
        try:
            await bot.edit_message_text(
                chat_id=admin_id,
                message_id=progress_msg.message_id,
                text=build_broadcast_final_report(
                    audience, total, sent, blocked, failed,
                ),
            )
        except Exception:
            pass


async def resume_running_jobs() -> None:
    """Called on startup. Spawns a worker for each interrupted broadcast."""
    for job in db.get_running_jobs():
        log.info(
            "resuming broadcast job %s for admin %s",
            job["id"],
            job["admin_id"],
        )
        asyncio.create_task(
            _run_broadcast(job["id"], job["admin_id"]),
            name=f"broadcast-{job['id']}",
        )


# ──────────────────────────────────────────────────────────────────
# Handlers
# ──────────────────────────────────────────────────────────────────

def register(dp: Dispatcher) -> None:
    @dp.callback_query(F.data == "admin:broadcast")
    async def on_start(cq: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(cq.from_user.id if cq.from_user else None):
            await cq.answer("Not authorized.")
            return
        await state.clear()
        await state.set_state(BroadcastFlow.composing)
        try:
            await cq.message.edit_text(
                build_broadcast_compose_prompt(),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="❌ Cancel", callback_data="bc:cancel"),
                ]]),
            )
        except Exception:
            pass
        await cq.answer()

    @dp.message(BroadcastFlow.composing, F.chat.type == "private")
    async def on_compose(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id if message.from_user else None):
            return

        payload = _serialize_message(message)
        if payload is None:
            await message.answer(
                "⚠️ Unsupported message. Send text or a photo with optional caption."
            )
            return

        counts = {
            "all": db.count_audience("all"),
            "active_7d": db.count_audience("active_7d"),
            "active_30d": db.count_audience("active_30d"),
        }
        await state.update_data(broadcast_payload=payload, broadcast_counts=counts)
        await state.set_state(None)  # exit composing; keep data for next steps

        # 1) Echo the message exactly as recipients will see it, with button.
        markup = _build_markup(payload)
        if payload["kind"] == "photo":
            await message.answer_photo(
                photo=payload["file_id"],
                caption=payload.get("text") or None,
                reply_markup=markup,
            )
        else:
            await message.answer(payload["text"], reply_markup=markup)

        # 2) Separate card for audience selection.
        await message.answer(
            build_broadcast_preview_text(),
            reply_markup=broadcast_audience_keyboard(counts),
        )

    @dp.callback_query(F.data.startswith("bc:audience:"))
    async def on_audience(cq: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(cq.from_user.id if cq.from_user else None):
            await cq.answer("Not authorized.")
            return
        audience = cq.data.rsplit(":", 1)[-1]
        data = await state.get_data()
        payload = data.get("broadcast_payload")
        counts = data.get("broadcast_counts") or {}
        if not payload:
            await cq.answer("Session expired. Start over with /admin.")
            return

        await state.update_data(broadcast_audience=audience)
        try:
            await cq.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await cq.message.answer(
            build_broadcast_confirm(audience, counts.get(audience, 0)),
            reply_markup=broadcast_confirm_keyboard(),
        )
        await cq.answer()

    @dp.callback_query(F.data == "bc:confirm")
    async def on_confirm(cq: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(cq.from_user.id if cq.from_user else None):
            await cq.answer("Not authorized.")
            return
        data = await state.get_data()
        payload = data.get("broadcast_payload")
        audience = data.get("broadcast_audience")
        counts = data.get("broadcast_counts") or {}
        if not payload or not audience:
            await cq.answer("Session expired. Start over with /admin.")
            return

        total = counts.get(audience, 0)
        job_id = db.create_broadcast_job(
            admin_id=cq.from_user.id,
            payload=payload,
            audience=audience,
            total=total,
        )
        await state.clear()
        try:
            await cq.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await cq.answer("Broadcast started!")
        asyncio.create_task(
            _run_broadcast(job_id, cq.from_user.id),
            name=f"broadcast-{job_id}",
        )

    @dp.callback_query(F.data == "bc:cancel")
    async def on_cancel(cq: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        try:
            await cq.message.edit_reply_markup(reply_markup=None)
            await cq.message.edit_text(build_broadcast_cancel_text())
        except Exception:
            pass
        await cq.answer("Cancelled.")