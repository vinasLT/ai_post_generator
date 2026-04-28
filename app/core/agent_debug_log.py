"""Foldable NDJSON debug logs for Cursor debug sessions (append-only)."""
import json
import os
import time

_DEBUG_PATHS = (
    "/home/ivanp/.cursor/debug-logs/debug-b22fdf.log",
    "/tmp/debug-b22fdf.ndjson",
)


def agent_debug_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict | None = None,
    run_id: str = "pre-fix",
) -> None:
    payload = {
        "sessionId": "b22fdf",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
    }
    line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"
    for path in _DEBUG_PATHS:
        try:
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
            return
        except OSError:
            continue
