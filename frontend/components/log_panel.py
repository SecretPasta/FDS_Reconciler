"""Live log panel — fetches /logs/recent on each render and displays results.

Auto-refresh is driven by the single st_autorefresh call in streamlit_app.py;
this component just reads and renders on every rerun.
"""
from __future__ import annotations

import streamlit as st

import api_client
from config import get_settings

_CATEGORIES = ["All", "retrieval", "llm", "pipeline", "error", "other"]

_LEVEL_ICON = {
    "DEBUG": "  ",
    "INFO": "  ",
    "WARNING": "! ",
    "ERROR": "X ",
    "CRITICAL": "XX",
}


def _format_line(entry: api_client.LogEntry) -> str:
    ts = entry.timestamp[11:19]  # HH:MM:SS from ISO-8601
    icon = _LEVEL_ICON.get(entry.level, "  ")
    return f"[{ts}] {icon}{entry.level:<8} {entry.module}  {entry.message}"


def render_log_panel(key_suffix: str = "") -> None:
    """
    Render the live log panel.
    key_suffix must be unique when this component is rendered more than once
    on the same page (e.g. once in each tab).
    """
    s = get_settings()

    st.markdown("#### Live Logs")

    col_filter, col_clear = st.columns([3, 1])
    with col_filter:
        category = st.selectbox(
            "Filter by category",
            _CATEGORIES,
            key=f"log_category_{key_suffix}",
            label_visibility="collapsed",
        )
    with col_clear:
        if st.button("Clear", key=f"log_clear_{key_suffix}", use_container_width=True):
            st.session_state[f"log_lines_{key_suffix}"] = []

    buf_key = f"log_lines_{key_suffix}"
    if buf_key not in st.session_state:
        st.session_state[buf_key] = []

    result = api_client.get_recent_logs(limit=s.max_log_lines)
    if isinstance(result, api_client.ApiError):
        # Backend unreachable — keep whatever we had
        pass
    else:
        entries = result
        if category != "All":
            entries = [e for e in entries if e.category == category]
        st.session_state[buf_key] = [_format_line(e) for e in entries[-s.max_log_lines :]]

    lines: list[str] = st.session_state[buf_key]
    text = "\n".join(lines) if lines else "(no logs yet — run a comparison or send a chat message)"

    st.text_area(
        "Logs",
        value=text,
        height=420,
        key=f"log_text_{key_suffix}",
        label_visibility="collapsed",
        disabled=True,
    )

    if lines:
        st.caption(f"{len(lines)} line(s) shown")
