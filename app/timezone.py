from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    BEIJING_TZ = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:
    BEIJING_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def ensure_beijing(dt: datetime) -> datetime:
    """Normalize incoming datetime to Beijing timezone."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BEIJING_TZ)
    return dt.astimezone(BEIJING_TZ)


def now_in_beijing() -> datetime:
    """Return current datetime in Beijing timezone."""
    return datetime.now(BEIJING_TZ)
