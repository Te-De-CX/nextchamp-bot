from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from .config import settings


def _base() -> str:
    return settings.nextchamp_frontend_url.rstrip("/")


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    base = _base()
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="🎮 Find Match",
                    web_app=WebAppInfo(url=f"{base}/dashboard/challenges?action=find"),
                ),
                KeyboardButton(
                    text="➕ Create Match",
                    web_app=WebAppInfo(url=f"{base}/dashboard/challenges?action=create"),
                ),
            ],
            [
                KeyboardButton(
                    text="💳 Deposit",
                    web_app=WebAppInfo(url=f"{base}/dashboard/wallet?action=deposit"),
                ),
                KeyboardButton(
                    text="💼 Balance",
                    web_app=WebAppInfo(url=f"{base}/dashboard/wallet"),
                ),
            ],
            [
                KeyboardButton(
                    text="💸 Withdraw",
                    web_app=WebAppInfo(url=f"{base}/dashboard/wallet?action=withdraw"),
                ),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Tap a button or type /help",
    )


# ──────────────────────────────────────────────────────────────────
# Admin (Phase 1b) — UNCHANGED
# ──────────────────────────────────────────────────────────────────

def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Users", callback_data="admin:users:0"),
            InlineKeyboardButton(text="📢 Broadcast", callback_data="admin:broadcast"),
        ],
        [InlineKeyboardButton(text="❌ Close", callback_data="admin:close")],
    ])


def users_list_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text="◀️ Prev", callback_data=f"admin:users:{page - 1}",
        ))
    nav.append(InlineKeyboardButton(
        text=f"{page + 1} / {total_pages}", callback_data="admin:noop",
    ))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(
            text="Next ▶️", callback_data=f"admin:users:{page + 1}",
        ))

    return InlineKeyboardMarkup(inline_keyboard=[
        nav,
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin:menu")],
    ])


def broadcast_audience_keyboard(counts: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"👥 All users ({counts.get('all', 0):,})",
            callback_data="bc:audience:all",
        )],
        [InlineKeyboardButton(
            text=f"🔥 Active 7d ({counts.get('active_7d', 0):,})",
            callback_data="bc:audience:active_7d",
        )],
        [InlineKeyboardButton(
            text=f"⭐ Active 30d ({counts.get('active_30d', 0):,})",
            callback_data="bc:audience:active_30d",
        )],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="bc:cancel")],
    ])


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Send Now", callback_data="bc:confirm"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="bc:cancel"),
        ],
    ])