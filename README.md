# NextChamp Telegram Bot

Auto-posts new public challenges from NextChamp to a Telegram channel, with an
inline **Challenge Now** button that deep-links to the match.

When a challenge is taken or cancelled, the bot edits the original post — the
button is replaced with a greyed-out **🔒 Challenge Closed** and the caption
updates to reflect the final status.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# fill in BOT_TOKEN and CHANNEL_ID
python main.py
```

1. Create a bot via [@BotFather](https://t.me/BotFather) → copy the token into `BOT_TOKEN`.
2. Add the bot as an **admin** of your channel (needs permission to post + edit).
3. Put the channel ID or `@username` into `CHANNEL_ID`.
4. (Optional) Drop your banner at `assets/challenge-banner.jpg` — the bot posts
   text-only if the file is missing.

## How it works

- Polls `GET /v1/matches` every `POLL_INTERVAL_MS` (default **5s**).
- On first run, records a baseline `createdAt` and **does not backfill** existing
  challenges. Only matches created after that timestamp get posted.
- For each tracked OPEN match: if it disappears from the public list, the bot
  fetches `GET /v1/matches/{id}` for the final status and edits the message.
- State (posted message IDs, baseline timestamp) persists in `data/state.json`.

## Layout

| File | Purpose |
| --- | --- |
| `main.py` | Entry point — sets up dispatcher + background poller |
| `bot/config.py` | Env var loading (pydantic-settings) |
| `bot/types.py` | Pydantic models for the NextChamp API |
| `bot/messages.py` | Caption templates & button labels (edit copy here) |
| `bot/api.py` | Async httpx client for `/v1/matches` |
| `bot/state.py` | JSON persistence + atomic writes |
| `bot/telegram_bot.py` | Bot instance + inline keyboards |
| `bot/poster.py` | Sends the challenge post |
| `bot/expirer.py` | Edits the message when a challenge closes |
| `bot/poller.py` | The 5s discovery + expiry loop |

## Deployment

Any always-on host: Railway, Fly.io, a $5 VPS, a Docker container.
**Note:** Render's free tier sleeps on inactivity, which will break the 5s
polling loop. Use a paid instance or a different host.