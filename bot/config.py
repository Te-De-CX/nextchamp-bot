from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str
    channel_id: str
    bot_username: str = "NextChampion_bot"

    # Shared secret used for the notifications endpoints:
    #   x-bot-secret: <bot_secret>
    bot_secret: str = ""

    nextchamp_api_url: str = "https://api.nextchampion.app"
    nextchamp_frontend_url: str = "https://nextchampion.app"

    # Short name of the Mini App registered in BotFather.
    # Used to build deep links: https://t.me/<bot>/<short>?startapp=<param>
    mini_app_short_name: str = "app"

    # Comma-separated numeric Telegram IDs of admins, e.g. "123456789,987654321"
    admin_telegram_ids: str = ""

    # Folder containing per-game images named {slug}.jpg
    games_media_dir: str | None = "./assets/games"
    # Fallback image when a game has no dedicated banner
    default_media_path: str | None = "./assets/default.jpg"
    # Optional welcome image for /start
    welcome_media_path: str | None = "./assets/welcome.jpg"

    # Public "learn more" link shown in /help
    help_url: str = "https://nextchampion.app/contact"

    poll_interval_ms: int = 5000
    state_file: str = "./data/state.json"
    db_file: str = "./data/bot.sqlite3"

    @field_validator(
        "games_media_dir",
        "default_media_path",
        "welcome_media_path",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def admin_ids(self) -> set[int]:
        if not self.admin_telegram_ids.strip():
            return set()
        out: set[int] = set()
        for chunk in self.admin_telegram_ids.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                out.add(int(chunk))
            except ValueError:
                # Ignore malformed entries rather than crash at startup
                pass
        return out


settings = Settings()