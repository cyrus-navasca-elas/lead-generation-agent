from __future__ import annotations

from datetime import datetime, timezone

from ulid import ULID


def new_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{str(ULID()).lower()}"
