import logging
from pathlib import Path

from .config import settings

log = logging.getLogger(__name__)

_SUPPORTED_EXT = ".jpg"

_games_map: dict[str, Path] = {}
_default_path: Path | None = None
_initialized = False


def init() -> None:
    """
    Scan GAMES_MEDIA_DIR + resolve DEFAULT_MEDIA_PATH. Idempotent.
    Logs a summary so you know what loaded and what's missing.
    """
    global _games_map, _default_path, _initialized
    if _initialized:
        return

    # ── Default image ────────────────────────────────────────
    if settings.default_media_path:
        p = Path(settings.default_media_path)
        if p.is_file():
            _default_path = p
            log.info("[media] default image: %s", p)
        else:
            log.warning(
                "[media] DEFAULT_MEDIA_PATH=%r not found — "
                "matches without a game image will post as text-only",
                settings.default_media_path,
            )
    else:
        log.info("[media] DEFAULT_MEDIA_PATH not set")

    # ── Per-game folder ──────────────────────────────────────
    if settings.games_media_dir:
        d = Path(settings.games_media_dir)
        if d.is_dir():
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() == _SUPPORTED_EXT:
                    _games_map[f.stem] = f
            if _games_map:
                log.info(
                    "[media] %d game image(s) loaded: %s",
                    len(_games_map),
                    ", ".join(sorted(_games_map)),
                )
            else:
                log.warning(
                    "[media] GAMES_MEDIA_DIR=%r contains no %s files",
                    settings.games_media_dir,
                    _SUPPORTED_EXT,
                )
        else:
            log.warning(
                "[media] GAMES_MEDIA_DIR=%r not found — "
                "all posts will use the default image",
                settings.games_media_dir,
            )
    else:
        log.info("[media] GAMES_MEDIA_DIR not set")

    _initialized = True


def resolve(game_slug: str | None) -> Path | None:
    """
    Return the image to attach for the given game slug.

    Priority:
      1. assets/games/{slug}.jpg
      2. DEFAULT_MEDIA_PATH
      3. None  → caller posts text-only
    """
    if game_slug:
        hit = _games_map.get(game_slug)
        if hit is not None:
            return hit
    return _default_path


def loaded_slugs() -> list[str]:
    return sorted(_games_map.keys())