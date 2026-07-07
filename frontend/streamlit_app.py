"""FDS Reconciler — Streamlit frontend.

Entry point: streamlit run streamlit_app.py
"""
from __future__ import annotations

import time

import streamlit as st
from streamlit_autorefresh import st_autorefresh

import api_client
from components.chat_panel import render_chat_panel
from components.comparison_view import render_comparison_view
from components.log_panel import render_log_panel
from config import get_settings

# ── page config — must be the very first Streamlit call ───────────────────────

st.set_page_config(
    page_title="FDS Reconciler",
    layout="wide",
    initial_sidebar_state="expanded",
)

s = get_settings()

# ── global auto-refresh — drives the log panel polling ────────────────────────
# Triggers a full page rerun every N ms. Widget state is preserved across reruns,
# so text inputs and forms are not disrupted.

st_autorefresh(interval=s.log_stream_poll_interval_ms, key="global_refresh")

# ── backend health — checked once per rerun, re-probed every 5 s ──────────────

_now = time.time()
if "backend_ok" not in st.session_state:
    st.session_state.backend_ok = api_client.backend_healthy()
    st.session_state.backend_check_ts = _now
elif _now - st.session_state.get("backend_check_ts", 0) > 5:
    st.session_state.backend_ok = api_client.backend_healthy()
    st.session_state.backend_check_ts = _now

if not st.session_state.backend_ok:
    st.error(
        f"Backend not reachable at **{s.backend_url}**. "
        "Start it with `docker compose up backend` "
        "or `uv run uvicorn app.main:app --reload` in the project root."
    )

# ── sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    dot_color = "limegreen" if st.session_state.backend_ok else "#e05555"
    status_label = "Reachable" if st.session_state.backend_ok else "Down"

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">'
        f'<div style="width:11px;height:11px;border-radius:50%;background:{dot_color};'
        f'box-shadow:0 0 6px {dot_color}"></div>'
        f'<span style="color:#ccc">Backend: <strong>{status_label}</strong></span>'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(s.backend_url)

    st.divider()

    st.markdown("**Session**")
    history_len = len(st.session_state.get("chat_history", []))
    st.metric("Chat turns", history_len)

    if st.button("Clear chat history", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

    st.divider()
    st.caption("FDS Reconciler v0.1.0")

# ── tabs ───────────────────────────────────────────────────────────────────────

tab_chat, tab_comparison = st.tabs(["Chat", "Comparison"])

with tab_chat:
    col_chat, col_logs = st.columns([0.60, 0.40])
    with col_chat:
        render_chat_panel()
    with col_logs:
        render_log_panel(key_suffix="chat")

with tab_comparison:
    col_comp, col_logs2 = st.columns([0.65, 0.35])
    with col_comp:
        render_comparison_view()
    with col_logs2:
        render_log_panel(key_suffix="comparison")
