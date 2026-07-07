"""Log ring-buffer, SSE stream, and polling endpoint.

The ring-buffer handler is attached at module import time AND survives any
subsequent logging.config.dictConfig() call (uvicorn calls its own dictConfig
after our app module is imported, which would otherwise wipe our handler).
"""
from __future__ import annotations

import asyncio
import json
import logging
import logging.config as _logging_config
from collections import deque
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/logs", tags=["logs"])

_BUFFER_SIZE = 500
_ring_buffer: deque[dict] = deque(maxlen=_BUFFER_SIZE)
_subscribers: set[asyncio.Queue] = set()


def _category(name: str, level: str) -> str:
    if level in ("ERROR", "CRITICAL"):
        return "error"
    n = name.lower()
    if "uvicorn" in n:
        return "other"
    if "retriev" in n:
        return "retrieval"
    if any(x in n for x in ("llm", "claude", "gemini", "chat.graph", "chat.synth")):
        return "llm"
    if any(x in n for x in ("pipeline", "comparison", "aligner", "judge", "ranker", "explainer", "indexing")):
        return "pipeline"
    return "other"


class LogEntry(BaseModel):
    timestamp: str
    level: str
    module: str
    message: str
    category: str


class _RingBufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "module": record.name,
                "message": record.getMessage(),
                "category": _category(record.name, record.levelname),
            }
            _ring_buffer.append(entry)
            for q in list(_subscribers):
                try:
                    q.put_nowait(entry)
                except (asyncio.QueueFull, Exception):  # noqa: BLE001
                    _subscribers.discard(q)
        except Exception:  # noqa: BLE001
            self.handleError(record)


_handler = _RingBufferHandler(level=logging.DEBUG)


def _reattach() -> None:
    """Add _handler to root and any non-propagating loggers we care about."""
    for name in ("", "uvicorn.access", "uvicorn.error", "uvicorn"):
        lg = logging.getLogger(name)
        if _handler not in lg.handlers:
            lg.addHandler(_handler)


# ── survive any logging.config.dictConfig() call made after this module loads ─
# Uvicorn (and our own create_app) call dictConfig which replaces root handlers.
# Wrapping dictConfig guarantees our handler is re-added after every such call.

_orig_dictConfig = _logging_config.dictConfig


def _patched_dictConfig(config: dict) -> None:  # type: ignore[override]
    _orig_dictConfig(config)
    _reattach()


_logging_config.dictConfig = _patched_dictConfig  # type: ignore[assignment]

# Attach immediately at import time so we capture logs from the very first request.
_reattach()


def attach_log_handler() -> None:
    """Public entry point kept for backwards compat — _reattach() now handles everything."""
    _reattach()


# ── SSE stream ─────────────────────────────────────────────────────────────────

async def _event_stream() -> AsyncGenerator[str, None]:
    q: asyncio.Queue[dict] = asyncio.Queue(maxsize=200)
    _subscribers.add(q)
    try:
        while True:
            try:
                entry = await asyncio.wait_for(q.get(), timeout=15.0)
                yield f"data: {json.dumps(entry)}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        _subscribers.discard(q)


@router.get("/stream")
async def stream_logs() -> StreamingResponse:
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/recent", response_model=list[LogEntry])
async def recent_logs(limit: int = Query(default=200, ge=1, le=500)) -> list[dict]:
    entries = list(_ring_buffer)
    return entries[-limit:]


@router.get("/debug")
async def debug_logs() -> dict:
    """Diagnostic endpoint — shows handler attachment state and buffer size."""
    root = logging.getLogger()
    return {
        "handler_attached": _handler in root.handlers,
        "root_handler_count": len(root.handlers),
        "buffer_size": len(_ring_buffer),
        "last_5": list(_ring_buffer)[-5:],
    }
