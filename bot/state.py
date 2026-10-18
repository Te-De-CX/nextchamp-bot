import json
import logging
from pathlib import Path

from .config import settings
from .types import State, TrackedMatch

log = logging.getLogger(__name__)

_state: State = State()


def _path() -> Path:
    return Path(settings.state_file)


def load() -> None:
    global _state
    p = _path()
    if not p.exists():
        _state = State()
        return
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        _state = State.model_validate(raw)
    except Exception as e:
        log.warning("state load failed (%s) — starting fresh", e)
        _state = State()


def save() -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(_state.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(p)  # atomic rename


def last_seen() -> str | None:
    return _state.last_seen_created_at


def set_last_seen(iso: str) -> None:
    _state.last_seen_created_at = iso
    save()


def track(match_id: str, entry: TrackedMatch) -> None:
    _state.tracked[match_id] = entry
    save()


def update_status(match_id: str, status: str) -> None:
    if match_id in _state.tracked:
        _state.tracked[match_id].status = status
        save()


def tracked_items() -> list[tuple[str, TrackedMatch]]:
    return list(_state.tracked.items())


def tracked_count() -> int:
    return len(_state.tracked)