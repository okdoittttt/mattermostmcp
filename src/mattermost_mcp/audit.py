from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _resolve_path() -> Path:
    raw = os.environ.get("MM_AUDIT_LOG_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".mattermost-mcp" / "audit.log"


def audit_log(action: str, **fields: Any) -> None:
    path = _resolve_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        **{k: v for k, v in fields.items() if k.lower() not in {"token", "authorization"}},
    }
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass
