"""Small display-formatting helpers shared by views."""

from __future__ import annotations

from datetime import datetime


def relative_time(when: datetime, now: datetime | None = None) -> str:
    """'just now', '5 min ago', 'today at 14:05', 'yesterday at 09:30',
    or '2026-09-28 14:05'."""
    now = now or datetime.now()
    seconds = (now - when).total_seconds()
    if seconds < 0:            # clock skew / file from the future
        return f"today at {when:%H:%M}" if when.date() == now.date() else f"{when:%Y-%m-%d %H:%M}"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if when.date() == now.date():
        return f"today at {when:%H:%M}"
    if (now.date() - when.date()).days == 1:
        return f"yesterday at {when:%H:%M}"
    return f"{when:%Y-%m-%d %H:%M}"
