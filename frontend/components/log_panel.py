"""Live log panel — plain render function, called from a top-level fragment."""
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
    Render the live log panel. Must be called from a top-level st.fragment so
    that the fragment has a stable identity and respects its tab/column context.
    key_suffix must be unique when rendered in more than one place on the page.
    """
    s = get_settings()

    st.markdown("#### Live Logs")

    col_filter, col_clear = st.columns([3, 1])
    with col_filter:
        category = st.selectbox(
            "Filter",
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
    if not isinstance(result, api_client.ApiError):
        entries = result
        if category != "All":
            entries = [e for e in entries if e.category == category]
        st.session_state[buf_key] = [_format_line(e) for e in entries[-s.max_log_lines:]]

    lines: list[str] = st.session_state[buf_key]
    text = "\n".join(lines) if lines else "(no logs yet)"

    st.markdown(
        f'<div style="'
        f"background:#0e1117;"
        f"border:1px solid #2a2d35;"
        f"border-radius:6px;"
        f"padding:10px 12px;"
        f"height:420px;"
        f"overflow-y:auto;"
        f"font-family:monospace;"
        f"font-size:0.78em;"
        f"color:#c8c8c8;"
        f"white-space:pre-wrap;"
        f"word-break:break-word;"
        f'">{text}</div>',
        unsafe_allow_html=True,
    )

    if lines:
        st.caption(f"{len(lines)} line(s)")
