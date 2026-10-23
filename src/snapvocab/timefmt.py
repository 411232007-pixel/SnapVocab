from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import TIMEZONE

_TZ = ZoneInfo(TIMEZONE)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_taipei(iso_utc: str) -> datetime:
    return datetime.fromisoformat(iso_utc).astimezone(_TZ)


def format_taipei(iso_utc: str) -> str:
    return to_taipei(iso_utc).strftime("%Y-%m-%d %H:%M") + " (Asia/Taipei, UTC+8)"
