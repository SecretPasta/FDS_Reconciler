"""Thin synchronous httpx wrapper around the FDS Reconciler backend.

All public functions return a typed result dataclass on success or an
ApiError on failure — raw exceptions never propagate into Streamlit.
httpx.Client (sync) is used intentionally: Streamlit's render loop is
synchronous, so async clients require event-loop plumbing that adds more
complexity than it saves at this scale.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from config import get_settings


# ── result types ──────────────────────────────────────────────────────────────

@dataclass
class ChatAnswer:
    answer: str
    citations: list[str]
    insufficient_context: bool
    elapsed_s: float


@dataclass
class ComparisonStats:
    total_matches: int
    total_diffs: int
    total_missing: int
    top_changes: list[dict] = field(default_factory=list)


@dataclass
class LogEntry:
    timestamp: str
    level: str
    module: str
    message: str
    category: str


@dataclass
class ApiError:
    message: str
    status_code: int | None = None

    def __str__(self) -> str:
        if self.status_code:
            return f"HTTP {self.status_code}: {self.message}"
        return self.message


# ── shared client factory ─────────────────────────────────────────────────────

def _client(timeout: float | None = None) -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        base_url=s.backend_url,
        timeout=timeout if timeout is not None else s.request_timeout_seconds,
    )


# ── public API ────────────────────────────────────────────────────────────────

def backend_healthy() -> bool:
    try:
        with _client(timeout=5) as c:
            return c.get("/docs").is_success
    except Exception:
        return False


def chat_single(query: str, doc_id: str) -> ChatAnswer | ApiError:
    t0 = time.perf_counter()
    try:
        with _client() as c:
            r = c.post("/chat/single", json={"query": query, "doc_id": doc_id})
            r.raise_for_status()
            d = r.json()
            return ChatAnswer(
                answer=d["answer"],
                citations=d.get("citations", []),
                insufficient_context=d.get("insufficient_context", False),
                elapsed_s=round(time.perf_counter() - t0, 1),
            )
    except httpx.HTTPStatusError as exc:
        return ApiError(message=exc.response.text, status_code=exc.response.status_code)
    except Exception as exc:
        return ApiError(message=str(exc))


def chat_cross(query: str) -> ChatAnswer | ApiError:
    t0 = time.perf_counter()
    try:
        with _client() as c:
            r = c.post("/chat/cross", json={"query": query})
            r.raise_for_status()
            d = r.json()
            return ChatAnswer(
                answer=d["answer"],
                citations=d.get("citations", []),
                insufficient_context=d.get("insufficient_context", False),
                elapsed_s=round(time.perf_counter() - t0, 1),
            )
    except httpx.HTTPStatusError as exc:
        return ApiError(message=exc.response.text, status_code=exc.response.status_code)
    except Exception as exc:
        return ApiError(message=str(exc))


def run_comparison(pdf_path: str, docx_path: str) -> ComparisonStats | ApiError:
    try:
        with _client() as c:
            r = c.post("/compare", json={"pdf_path": pdf_path, "docx_path": docx_path})
            r.raise_for_status()
            data = r.json()
            result = data["result"]
            summary = data["summary"]
            return ComparisonStats(
                total_matches=len(result["match"]),
                total_diffs=len(result["diff"]),
                total_missing=len(result["missing"]),
                top_changes=summary.get("top_changes", []),
            )
    except httpx.HTTPStatusError as exc:
        return ApiError(message=exc.response.text, status_code=exc.response.status_code)
    except Exception as exc:
        return ApiError(message=str(exc))


def get_summary() -> ComparisonStats | ApiError:
    try:
        with _client() as c:
            r = c.get("/summary")
            r.raise_for_status()
            data = r.json()["summary"]
            return ComparisonStats(
                total_matches=data["total_matches"],
                total_diffs=data["total_diffs"],
                total_missing=data["total_missing"],
                top_changes=data.get("top_changes", []),
            )
    except httpx.HTTPStatusError as exc:
        return ApiError(message=exc.response.text, status_code=exc.response.status_code)
    except Exception as exc:
        return ApiError(message=str(exc))


def get_recent_logs(limit: int = 200) -> list[LogEntry] | ApiError:
    try:
        with _client(timeout=5) as c:
            r = c.get("/logs/recent", params={"limit": limit})
            r.raise_for_status()
            return [LogEntry(**e) for e in r.json()]
    except Exception as exc:
        return ApiError(message=str(exc))
