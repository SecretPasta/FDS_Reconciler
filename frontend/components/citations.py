"""Render citation strings as styled inline pills."""
from __future__ import annotations

_PILL_CSS = (
    "display:inline-block;"
    "background:#1e3a5f;"
    "color:#7ec8e3;"
    "border-radius:4px;"
    "padding:2px 8px;"
    "margin:2px 3px 2px 0;"
    "font-size:0.78em;"
    "font-family:monospace;"
    "white-space:nowrap;"
    "border:1px solid #2a5580;"
)


def citation_pills_html(citations: list[str]) -> str:
    """Return an HTML string of pill-styled citation spans, or empty string if none."""
    if not citations:
        return ""
    pills = [f'<span style="{_PILL_CSS}">{c}</span>' for c in citations]
    return '<div style="margin-top:8px;line-height:2">' + "".join(pills) + "</div>"
