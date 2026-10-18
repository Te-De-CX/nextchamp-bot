from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import settings
from .types import Match, MatchSnapshot


OPEN_BUTTON_TEXT = "Challenge Now 🎮"
CLOSED_BUTTON_TEXT = "🔒 Challenge Closed"
CLOSED_BUTTON_TOAST = "This challenge is no longer active."
CLOSED_CALLBACK_DATA = "challenge:closed"


def esc(value) -> str:
    return escape(str(value if value is not None else ""))


def _fmt_money(amount: float, currency: str) -> str:
    return f"{int(amount):,} {currency}"


def _creator_display(match: Match) -> str:
    c = match.creator
    name = None
    if c:
        if c.profile and c.profile.displayName:
            name = c.profile.displayName.strip()
        elif c.username:
            name = c.username.strip()
    if not name:
        name = "Anonymous"
    if c and c.username:
        return f"{name} ({c.username})"
    return name


def snapshot_of(match: Match) -> MatchSnapshot:
    prize = None
    if match.prizeAmount and match.prizeAmount > 0:
        prize = _fmt_money(match.prizeAmount, match.currency)

    return MatchSnapshot(
        game_name=(match.game.name if match.game else None) or "Unknown game",
        stake_label=_fmt_money(match.stakeAmount, match.currency),
        prize_label=prize,
        creator_display=_creator_display(match),
    )


def build_challenge_caption(match: Match) -> str:
    s = snapshot_of(match)
    lines = [
        "🎮 <b>NEW CHALLENGE</b>",
        "",
        f"🕹 <b>{esc(s.game_name)}</b>",
        f"💰 Challenge Amount: <b>{esc(s.stake_label)}</b>",
    ]
    if s.prize_label:
        lines.append(f"🏆 Prize: <b>{esc(s.prize_label)}</b>")
    lines.append(f"👤 Creator: {esc(s.creator_display)}")
    lines.extend(["", "Tap below to accept this challenge."])
    return "\n".join(lines)


def _expiry_reason(status: str) -> tuple[str, str, str]:
    if status == "CANCELLED":
        return "❌", "CHALLENGE CANCELLED", "The creator cancelled this challenge."
    if status == "EXPIRED":
        return "⌛", "CHALLENGE EXPIRED", "This challenge expired before an opponent joined."
    if status == "REFUNDED":
        return "↩️", "CHALLENGE VOIDED", "Stakes were refunded. This challenge is closed."
    return "⏳", "CHALLENGE TAKEN", "An opponent joined. This challenge is no longer available."


def build_expired_caption(snapshot: MatchSnapshot, status: str) -> str:
    emoji, title, body = _expiry_reason(status)
    return "\n".join([
        f"{emoji} <b>{title}</b>",
        "",
        f"🕹 {esc(snapshot.game_name)}",
        f"💰 Challenge Amount: {esc(snapshot.stake_label)}",
        f"👤 Creator: {esc(snapshot.creator_display)}",
        "",
        f"<i>{body}</i>",
    ])


# ──────────────────────────────────────────────────────────────────
# User-facing copy (Phase 1a)
# ──────────────────────────────────────────────────────────────────

def build_welcome_caption(first_name: str | None) -> str:
    name = (first_name or "").strip() or "there"
    return "\n".join([
        f"👋 <b>Welcome to NextChamp, {esc(name)}!</b>",
        "",
        "🏆 Challenge Real Opponents. Play. Compete. Prove Your Skills. Become a Champion!",
        "",
        "Use the buttons below to get started 👇",
    ])


def build_help_text() -> str:
    return "\n".join([
        "<b>How NextChamp works</b>",
        "",
        "🎮 <b>Find Match</b> — browse open challenges and join one.",
        "➕ <b>Create Match</b> — set your stake, rules, and open a challenge.",
        "💳 <b>Deposit</b> — fund your wallet (Paystack supported).",
        "💼 <b>Balance</b> — view your wallet and transaction ledger.",
        "💸 <b>Withdraw</b> — cash out your winnings.",
        "",
        "Every button opens the NextChamp Mini App right here in Telegram.",
        "",
        f"📖 Learn more: <a href=\"{esc(settings.help_url)}\">NextChamp</a>",
    ])


# ──────────────────────────────────────────────────────────────────
# Admin panel copy (Phase 1b)
# ──────────────────────────────────────────────────────────────────

_AUDIENCE_LABELS = {
    "all": "All users",
    "active_7d": "Active last 7 days",
    "active_30d": "Active last 30 days",
}


def build_admin_menu(total: int, blocked: int) -> str:
    return "\n".join([
        "🛠 <b>Admin Panel</b>",
        "",
        f"👥 Users: <b>{total:,}</b> · 🚫 Blocked: <b>{blocked:,}</b>",
        "",
        "Choose an action below.",
    ])


def build_users_page(users: list[dict], page: int, total_pages: int, total: int) -> str:
    lines = [f"👥 <b>Users</b> ({total:,} total)", ""]
    if not users:
        lines.append("No users yet.")
    else:
        start = page * 20 + 1
        for i, u in enumerate(users, start=start):
            username = f"@{u['username']}" if u.get("username") else "(no username)"
            name = u.get("first_name") or "—"
            started = (u.get("started_at") or "")[:10]
            flag = " 🚫" if u.get("is_blocked") else ""
            lines.append(f"{i}. {esc(name)} · {esc(username)}{flag}")
            lines.append(f"    ID: <code>{u['telegram_id']}</code> · joined {started}")
    lines.append("")
    lines.append(f"Page {page + 1} of {total_pages}")
    return "\n".join(lines)


def build_broadcast_compose_prompt() -> str:
    return "\n".join([
        "📢 <b>New Broadcast</b>",
        "",
        "Send me the message you want to broadcast.",
        "",
        "You can send:",
        "• Plain text",
        "• A photo with optional caption",
        "",
        "To add an inline button, end your message with:",
        "<code>[Label](https://example.com)</code>",
        "",
        "Example:",
        "<code>🎉 New promo! Tap below to play now.\n[Play Now](https://t.me/NextChampion_bot/app?startapp=find)</code>",
    ])


def build_broadcast_preview_text() -> str:
    return "📢 <b>Preview ready.</b> Choose your audience below:"


def build_broadcast_confirm(audience: str, count: int) -> str:
    label = _AUDIENCE_LABELS.get(audience, audience)
    return "\n".join([
        "⚠️ <b>Confirm Broadcast</b>",
        "",
        f"Audience: <b>{esc(label)}</b>",
        f"Recipients: <b>{count:,}</b>",
        "",
        "This cannot be undone.",
    ])


def build_broadcast_progress(
    audience: str, done: int, total: int, sent: int, blocked: int, failed: int
) -> str:
    label = _AUDIENCE_LABELS.get(audience, audience)
    pct = int((done / total) * 100) if total else 0
    return "\n".join([
        "📢 <b>Broadcasting…</b>",
        "",
        f"Audience: {esc(label)}",
        f"Progress: <b>{done:,} / {total:,}</b> ({pct}%)",
        "",
        f"✅ Sent: {sent:,}",
        f"🚫 Blocked: {blocked:,}",
        f"❌ Failed: {failed:,}",
    ])


def build_broadcast_final_report(
    audience: str, total: int, sent: int, blocked: int, failed: int
) -> str:
    label = _AUDIENCE_LABELS.get(audience, audience)
    return "\n".join([
        "✅ <b>Broadcast Complete</b>",
        "",
        f"Audience: {esc(label)}",
        f"Total attempted: <b>{total:,}</b>",
        "",
        f"✅ Sent: {sent:,}",
        f"🚫 Blocked: {blocked:,}",
        f"❌ Failed: {failed:,}",
    ])


def build_broadcast_cancel_text() -> str:
    return "❌ Broadcast cancelled."


# ──────────────────────────────────────────────────────────────────
# Notifications (Phase 2)
# ──────────────────────────────────────────────────────────────────

_NOTIF_EMOJI = {
    # ── Wallet & Treasury ──
    "DEPOSIT_CONFIRMED": "💰",
    "WITHDRAWAL_REQUESTED": "⏳",
    # Defensive — not currently emitted, kept in case the backend adds them:
    "WITHDRAWAL_APPROVED": "💸",
    "WITHDRAWAL_REJECTED": "❌",

    # ── Match Lobby & Active Gameplay ──
    "CHALLENGE_ACCEPTED": "⚔️",
    "ROOM_CODE_SET": "🔑",
    "OPPONENT_READY": "✅",
    "MATCH_ACTIVE": "🎮",

    # ── Post-Match & Result Submissions ──
    "RESULT_SUBMISSION_REQUIRED": "📝",
    "RESULT_SUBMITTED_BY_OPPONENT": "📨",

    # ── Disputes ──
    "DISPUTE_OPENED": "⚠️",
    "DISPUTE_EVIDENCE_SUBMITTED": "📎",
    "DISPUTE_RESOLVED": "✅",

    # ── Match Outcomes & Settlements ──
    "MATCH_WON": "🏆",
    "MATCH_LOST": "💔",
    "MATCH_DRAW": "🤝",
    "MATCH_CANCELLED": "❌",

    # ── System ──
    "BROADCAST": "📢",
}


# Optional guidance appended below certain notification messages.
# The message body itself comes from the backend — this is bot-side
# editorial text that helps users know what to do next.
_NOTIF_SUFFIX = {
    "CHALLENGE_ACCEPTED": "👉 Set the room code now to start the match.",
    "OPPONENT_READY": "👉 Enter the room code and confirm ready in the app.",
    "DISPUTE_OPENED": "👉 Upload your proof to support your claim.",
    "DISPUTE_EVIDENCE_SUBMITTED": "👉 Upload your evidence to respond.",
}


def _mini_app_link(startapp: str) -> str:
    """
    Build a t.me Mini App deep link.

    Example: https://t.me/NextChampion_bot/app?startapp=join_<uuid>
    Telegram opens the Mini App and delivers `startapp` to the frontend
    as `initDataUnsafe.start_param` / `tgWebAppStartParam` in the URL.
    """
    return (
        f"https://t.me/{settings.bot_username}/{settings.mini_app_short_name}"
        f"?startapp={startapp}"
    )


def render_notification(notif: dict) -> str:
    """
    Render a notification into an HTML message body.

    Backend already gives us `title` and `message`, fully composed.
    We prepend an emoji based on eventType, and append optional
    bot-side guidance text from _NOTIF_SUFFIX if the event has one.
    """
    event_type = str(notif.get("eventType") or "").strip()
    emoji = _NOTIF_EMOJI.get(event_type, "🔔")

    title = (notif.get("title") or event_type.replace("_", " ").title() or "Notification").strip()
    message = (notif.get("message") or "").strip()

    lines = [f"{emoji} <b>{esc(title)}</b>"]
    if message:
        lines.extend(["", esc(message)])

    suffix = _NOTIF_SUFFIX.get(event_type)
    if suffix:
        lines.extend(["", f"<i>{esc(suffix)}</i>"])

    return "\n".join(lines)


def build_notification_button(notif: dict) -> InlineKeyboardMarkup | None:
    """
    Optional inline button:
      - data.matchId present → "View Match →"  via Mini App deep link
      - data.reference/amount → "Open Wallet →" via Mini App deep link
      - otherwise              → no button
    """
    data = notif.get("data") or {}

    match_id = data.get("matchId")
    if match_id:
        url = _mini_app_link(f"join_{match_id}")
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="View Match →", url=url),
        ]])

    if data.get("reference") or data.get("amount") is not None:
        url = _mini_app_link("balance")
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Open Wallet →", url=url),
        ]])

    return None