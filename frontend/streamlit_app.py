"""FDS Reconciler — Streamlit frontend.

Entry point: streamlit run streamlit_app.py

Fragment rules: @st.fragment instances must be defined at module top-level so
Streamlit assigns them stable identities. Fragments defined inside functions or
called inside tab/column contexts lose that context when they auto-rerun.
"""
from __future__ import annotations

import streamlit as st

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
_poll_s = max(1, s.log_stream_poll_interval_ms // 1000)


# ── top-level fragments — stable identities, respect their render location ────

@st.fragment(run_every=5)
def _backend_banner() -> None:
    ok = api_client.backend_healthy()
    st.session_state.backend_ok = ok
    if not ok:
        st.error(
            f"Backend not reachable at **{s.backend_url}**. "
            "Start it with `uv run uvicorn app.main:app --reload` in the project root."
        )


@st.fragment(run_every=_poll_s)
def _log_panel_chat() -> None:
    render_log_panel(key_suffix="chat")


@st.fragment(run_every=_poll_s)
def _log_panel_comparison() -> None:
    render_log_panel(key_suffix="comparison")


# ── backend health banner (top of page) ───────────────────────────────────────

_backend_banner()

# ── sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    ok = st.session_state.get("backend_ok", False)
    dot_color = "limegreen" if ok else "#e05555"
    status_label = "Reachable" if ok else "Down"

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
        _log_panel_chat()

with tab_comparison:
    col_comp, col_logs2 = st.columns([0.65, 0.35])
    with col_comp:
        render_comparison_view()
    with col_logs2:
        _log_panel_comparison()
