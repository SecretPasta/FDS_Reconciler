"""Comparison tab — trigger pipeline, load cached summary, display results."""
from __future__ import annotations

import streamlit as st

import api_client
from components.citations import citation_pills_html
from config import get_settings

_VERDICT_COLOR = {
    "DIFF": "#3a6fd8",
    "MISSING": "#8b5cf6",
    "MATCH": "#22c55e",
}


def _stat_card_html(value: int, label: str, number_color: str, bg: str) -> str:
    return (
        f'<div style="text-align:center;background:{bg};border-radius:8px;padding:28px 16px">'
        f'<div style="font-size:3.5rem;font-weight:700;color:{number_color};line-height:1">'
        f"{value}</div>"
        f'<div style="color:#aaa;margin-top:8px;font-size:0.95em;letter-spacing:0.08em">'
        f"{label}</div>"
        f"</div>"
    )


def _render_stat_cards(stats: api_client.ComparisonStats) -> None:
    col_m, col_d, col_ms = st.columns(3)
    with col_m:
        st.markdown(
            _stat_card_html(stats.total_matches, "MATCH", "#22c55e", "#1a2d1a"),
            unsafe_allow_html=True,
        )
    with col_d:
        st.markdown(
            _stat_card_html(stats.total_diffs, "DIFF", "#3a6fd8", "#1a2240"),
            unsafe_allow_html=True,
        )
    with col_ms:
        st.markdown(
            _stat_card_html(stats.total_missing, "MISSING", "#8b5cf6", "#2d1a40"),
            unsafe_allow_html=True,
        )


def _render_top_changes(changes: list[dict]) -> None:
    st.markdown("#### Top 10 Changes")
    for change in changes:
        verdict = change.get("verdict", "DIFF")
        color = _VERDICT_COLOR.get(verdict, "#888888")
        rank = change.get("rank", "?")
        summary = change.get("summary", "")
        label = f"#{rank} [{verdict}]  {summary}"

        with st.expander(label):
            badge_html = (
                f'<span style="background:{color};color:#fff;border-radius:4px;'
                f'padding:2px 10px;font-size:0.8em;font-weight:bold">{verdict}</span>'
            )
            st.markdown(badge_html, unsafe_allow_html=True)
            st.markdown(f"**{summary}**")

            why = change.get("why_it_matters", "")
            if why:
                st.markdown(f"*{why}*")

            citations = change.get("citations", [])
            if citations:
                st.markdown(citation_pills_html(citations), unsafe_allow_html=True)


def render_comparison_view() -> None:
    s = get_settings()

    st.markdown("### Comparison")

    col_run, col_load = st.columns(2)
    with col_run:
        run_clicked = st.button(
            "Run new comparison",
            use_container_width=True,
            type="primary",
            help=f"Triggers POST /compare with the configured sample files",
        )
    with col_load:
        load_clicked = st.button(
            "Load cached summary",
            use_container_width=True,
            help="Fetches GET /summary — only works after a comparison has been run",
        )

    if run_clicked:
        with st.spinner("Running comparison pipeline — this takes 1-3 minutes..."):
            result = api_client.run_comparison(
                s.comparison_pdf_path,
                s.comparison_docx_path,
            )
        if isinstance(result, api_client.ApiError):
            if result.status_code == 422:
                st.error(
                    f"Backend could not find the sample files at the configured paths.\n\n"
                    f"PDF: `{s.comparison_pdf_path}`\n\n"
                    f"DOCX: `{s.comparison_docx_path}`\n\n"
                    "Set `COMPARISON_PDF_PATH` and `COMPARISON_DOCX_PATH` in your `.env` "
                    "to paths that the backend process can access."
                )
            else:
                st.error(f"Comparison failed: {result}")
        else:
            st.session_state.comparison_stats = result
            st.success("Comparison complete.")
            st.rerun()

    if load_clicked:
        with st.spinner("Loading cached summary..."):
            result = api_client.get_summary()
        if isinstance(result, api_client.ApiError):
            if result.status_code == 404:
                st.warning(
                    "No comparison cached on the backend yet. "
                    "Click **Run new comparison** to run the pipeline first."
                )
            else:
                st.error(f"Failed to load summary: {result}")
        else:
            st.session_state.comparison_stats = result
            st.rerun()

    if "comparison_stats" in st.session_state:
        stats: api_client.ComparisonStats = st.session_state.comparison_stats
        st.divider()
        _render_stat_cards(stats)
        if stats.top_changes:
            st.divider()
            _render_top_changes(stats.top_changes)
    else:
        st.markdown(
            '<div style="text-align:center;color:#555;padding:60px 0">'
            "Run a comparison or load a cached summary to see results here."
            "</div>",
            unsafe_allow_html=True,
        )
