from __future__ import annotations

import json
import re
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path


def load_config(path: str) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        example = Path("config.example.json")
        if example.exists():
            return json.loads(example.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"Config file not found: {path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def month_bounds(value: str | None, default: str = "previous") -> tuple[date, date, str]:
    if not value and default == "previous":
        first_this_month = date.today().replace(day=1)
        last_prev = first_this_month - timedelta(days=1)
        start = last_prev.replace(day=1)
    elif value:
        start = _parse_month(value)
    else:
        start = date.today().replace(day=1)
    end = start.replace(day=monthrange(start.year, start.month)[1])
    return start, end, start.strftime("%B %Y")


def week_bounds(value: str | None, days: int = 7) -> tuple[date, date, str]:
    """Return the requested day period ending on value, or today when value is omitted."""
    if value:
        end = date.fromisoformat(value.strip())
    else:
        end = date.today()
    days = max(1, days)
    start = end - timedelta(days=days - 1)
    return start, end, f"{start.isoformat()} to {end.isoformat()}"


def _parse_month(value: str) -> date:
    value = value.strip()
    iso = re.fullmatch(r"(\d{4})-(\d{1,2})", value)
    if iso:
        return date(int(iso.group(1)), int(iso.group(2)), 1)
    for fmt in ("%B %Y", "%b %Y"):
        try:
            from datetime import datetime
            parsed = datetime.strptime(value, fmt)
            return date(parsed.year, parsed.month, 1)
        except ValueError:
            pass
    raise ValueError("Month must look like 'April 2026' or '2026-04'.")
