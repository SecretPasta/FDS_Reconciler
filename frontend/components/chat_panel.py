"""Chat panel — mode selector, message history, and input form."""
from __future__ import annotations

import streamlit as st

import api_client
from components.citations import citation_pills_html

_MODES: dict[str, tuple[str, str | None]] = {
    "Single-doc V0 (PDF)": ("single", "A"),
    "Single-doc V5 (DOCX)": ("single", "B"),
    "Cross-doc comparison": ("cross", None),
}

# Card background and accent colours by message state
_STYLE_NORMAL = ("#1a1d23", "#7ec8e3")
_STYLE_WARN = ("#2d2500", "#f0a500")
_STYLE_ERROR = ("#2d1b1b", "#e05555")


def _card_html(msg: dict) -> str:
    if msg.get("is_error"):
        bg, accent = _STYLE_ERROR
    elif msg.get("insufficient_context"):
        bg, accent = _STYLE_WARN
    else:
        bg, accent = _STYLE_NORMAL

    elapsed = msg.get("elapsed_s", "")
    elapsed_badge = (
        f'<span style="float:right;font-size:0.72em;color:#555;font-family:monospace">'
        f"{elapsed}s</span>"
        if elapsed
        else ""
    )

    question_html = (
        f'<div style="color:#ffffff;font-weight:bold;margin-bottom:8px">'
        f'{msg["question"]}</div>'
    )

    if msg.get("is_error"):
        body_html = (
            f'<div style="color:#e05555">Error: {msg.get("answer","")}</div>'
        )
    elif msg.get("insufficient_context"):
        body_html = (
            '<div style="color:#f0a500;font-weight:bold;margin-bottom:4px">'
            "No answer in context</div>"
            f'<div style="color:#aaa;font-size:0.9em">{msg.get("answer","")}</div>'
        )
    else:
        body_html = f'<div style="color:#e0e0e0">{msg.get("answer","")}</div>'

    citations_html = citation_pills_html(msg.get("citations", []))

    return (
        f'<div style="background:{bg};border-left:3px solid {accent};'
        f'border-radius:6px;padding:12px 16px;margin:8px 0">'
        f'<div style="color:{accent};font-size:0.72em;font-weight:bold;margin-bottom:4px">'
        f'{msg["mode_label"]}{elapsed_badge}</div>'
        f"{question_html}"
        f"{body_html}"
        f"{citations_html}"
        f"</div>"
    )


def render_chat_panel() -> None:
    st.markdown("### Chat")

    mode_label = st.radio(
        "Mode",
        list(_MODES.keys()),
        horizontal=True,
        key="chat_mode",
        label_visibility="collapsed",
    )

    st.divider()

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # History
    if st.session_state.chat_history:
        for msg in st.session_state.chat_history:
            st.markdown(_card_html(msg), unsafe_allow_html=True)
    else:
        st.markdown(
            '<div style="color:#555;text-align:center;padding:32px 0">'
            "No messages yet. Ask a question below."
            "</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # Input — st.form prevents reruns on every keystroke
    with st.form("chat_input_form", clear_on_submit=True):
        query = st.text_input(
            "Question",
            placeholder="Ask anything about the FDS documents...",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Send", use_container_width=True, type="primary")

    if submitted and query.strip():
        mode, doc_id = _MODES[mode_label]
        with st.spinner("Querying..."):
            if mode == "single" and doc_id:
                result = api_client.chat_single(query.strip(), doc_id)
            else:
                result = api_client.chat_cross(query.strip())

        if isinstance(result, api_client.ApiError):
            st.session_state.chat_history.append({
                "mode_label": mode_label,
                "question": query.strip(),
                "answer": str(result),
                "citations": [],
                "insufficient_context": False,
                "is_error": True,
                "elapsed_s": "",
            })
        else:
            st.session_state.chat_history.append({
                "mode_label": mode_label,
                "question": query.strip(),
                "answer": result.answer,
                "citations": result.citations,
                "insufficient_context": result.insufficient_context,
                "is_error": False,
                "elapsed_s": result.elapsed_s,
            })
        st.rerun()
