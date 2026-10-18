from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict


MatchStatus = Literal[
    "OPEN", "FULL", "RULES_PENDING", "READY", "ACTIVE",
    "RESULT_PENDING", "CONFIRMED", "SETTLING", "SETTLED",
    "DISPUTE", "UNDER_REVIEW", "RESOLVED", "CANCELLED",
    "REFUNDED", "EXPIRED",
]


class _Base(BaseModel):
    # `extra="ignore"` is pydantic v2's default, but we set it explicitly:
    # the NextChamp API leaks `email` / `passwordHash` on creator &
    # participants. Declaring only the fields we need means nothing
    # sensitive ever lands in memory, logs, or the state file.
    model_config = ConfigDict(extra="ignore")


class Game(_Base):
    name: str
    slug: str
    publisher: Optional[str] = None


class CreatorProfile(_Base):
    displayName: Optional[str] = None
    avatarUrl: Optional[str] = None


class Creator(_Base):
    username: Optional[str] = None
    profile: Optional[CreatorProfile] = None


class Match(_Base):
    id: str
    visibility: Optional[str] = None
    stakeAmount: float
    prizeAmount: Optional[float] = None
    currency: str
    status: str
    createdAt: str
    game: Optional[Game] = None
    creator: Optional[Creator] = None


class MatchSnapshot(_Base):
    game_name: str
    stake_label: str
    prize_label: Optional[str] = None
    creator_display: str


class TrackedMatch(_Base):
    message_id: int
    had_photo: bool
    status: str
    created_at: str
    posted_at: str
    snapshot: MatchSnapshot


class State(_Base):
    last_seen_created_at: Optional[str] = None
    tracked: dict[str, TrackedMatch] = {}