"""Log ring-buffer, SSE stream, and polling endpoint.

Attach attach_log_handler() in create_app() so all app logs flow into the
in-memory buffer and are available to connected clients.
"""
from __future__ import annotations

import asyncio
import json
import logging
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
            dead: list[asyncio.Queue] = []
            for q in _subscribers:
                try:
                    q.put_nowait(entry)
                except asyncio.QueueFull:
                    pass
                except Exception:  # noqa: BLE001
                    dead.append(q)
            for q in dead:
                _subscribers.discard(q)
        except Exception:  # noqa: BLE001
            self.handleError(record)


_handler = _RingBufferHandler(level=logging.DEBUG)


def attach_log_handler() -> None:
    """Install the ring-buffer handler on the root logger. Safe to call multiple times."""
    root = logging.getLogger()
    if _handler not in root.handlers:
        root.addHandler(_handler)


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
    """Server-Sent Events stream of log entries as they arrive."""
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/recent", response_model=list[LogEntry])
async def recent_logs(limit: int = Query(default=200, ge=1, le=500)) -> list[dict]:
    """Return the last N log entries as JSON. Used by the Streamlit frontend for polling."""
    entries = list(_ring_buffer)
    return entries[-limit:]
