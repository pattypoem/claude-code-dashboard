"""Jinja2 template filters."""

from datetime import datetime, timezone


def timeago(value: str) -> str:
    """Convert ISO timestamp to relative time string."""
    if not value:
        return "unknown"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - dt
        seconds = int(diff.total_seconds())

        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            mins = seconds // 60
            return f"{mins}m ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours}h ago"
        elif seconds < 604800:
            days = seconds // 86400
            return f"{days}d ago"
        elif seconds < 2592000:
            weeks = seconds // 604800
            return f"{weeks}w ago"
        else:
            return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return str(value)[:10] if value else "unknown"


def format_date(value: str) -> str:
    """Format ISO timestamp as readable date."""
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(value)[:16]


def format_number(value) -> str:
    """Format number with comma separators."""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


def truncate_text(value: str, length: int = 100) -> str:
    """Truncate text with ellipsis."""
    if not value or len(value) <= length:
        return value or ""
    return value[:length].rstrip() + "..."


def format_tokens(value) -> str:
    """Compact token count: 1234 -> '1.2K', 1_234_567 -> '1.2M'."""
    try:
        n = int(value)
    except (ValueError, TypeError):
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def format_duration(ms: int) -> str:
    """Format milliseconds to human readable duration."""
    if not ms:
        return ""
    seconds = ms // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining_mins = minutes % 60
    if hours < 24:
        return f"{hours}h {remaining_mins}m"
    days = hours // 24
    remaining_hours = hours % 24
    return f"{days}d {remaining_hours}h"


def register_filters(app):
    """Register all custom filters with the Flask app."""
    app.jinja_env.filters["timeago"] = timeago
    app.jinja_env.filters["format_date"] = format_date
    app.jinja_env.filters["format_number"] = format_number
    app.jinja_env.filters["truncate_text"] = truncate_text
    app.jinja_env.filters["format_duration"] = format_duration
    app.jinja_env.filters["format_tokens"] = format_tokens
