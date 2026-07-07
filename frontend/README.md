# FDS Reconciler — Frontend

Streamlit UI for the FDS Reconciler. Runs as a separate service and communicates with the FastAPI backend over HTTP.

---

## Prerequisites

- Python 3.11+
- `uv` installed (`pip install uv` or see [astral.sh/uv](https://astral.sh/uv))
- The backend running at `http://localhost:8000` (or whichever URL you configure)

---

## Local development

```bash
# From the frontend/ directory:

# 1. Install dependencies
uv sync

# 2. Configure environment
cp .env.example .env
# Edit .env — set BACKEND_URL, and set COMPARISON_PDF_PATH / COMPARISON_DOCX_PATH
# to absolute local paths where the backend can find the sample files.

# 3. Run
uv run streamlit run streamlit_app.py
```

The UI is available at `http://localhost:8501`.

### Important: comparison file paths

`COMPARISON_PDF_PATH` and `COMPARISON_DOCX_PATH` must be paths as seen by the **backend process**, not the frontend. When running both locally, set them to absolute local paths:

```
COMPARISON_PDF_PATH=C:\Projects\SDR\samples\FDS_PriceBook_V0.pdf
COMPARISON_DOCX_PATH=C:\Projects\SDR\samples\FDS_PriceBook_V5.docx
```

In Docker the defaults (`/app/samples/...`) work without changes.

---

## Running with Docker

From the project root:

```bash
docker compose up
```

This starts both services. The frontend is available at `http://localhost:8501`.

---

## Layout

**Chat tab** — 60/40 split:
- Left: mode selector (Single-doc V0 / V5 / Cross-doc), chat history as styled cards, query input
- Right: live log panel polling `/logs/recent` every 2 s

**Comparison tab** — 65/35 split:
- Left: run/load buttons, stat cards (MATCH / DIFF / MISSING counts), top-10 expanders
- Right: same live log panel

**Sidebar**: backend status dot (green/red), session stats, clear-history button.

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `BACKEND_URL` | `http://localhost:8000` | FastAPI backend URL |
| `REQUEST_TIMEOUT_SECONDS` | `180` | httpx request timeout |
| `LOG_STREAM_POLL_INTERVAL_MS` | `2000` | Log panel refresh interval |
| `MAX_LOG_LINES` | `200` | Max lines shown in log panel |
| `COMPARISON_PDF_PATH` | `/app/samples/FDS_PriceBook_V0.pdf` | Backend-side path to V0 PDF |
| `COMPARISON_DOCX_PATH` | `/app/samples/FDS_PriceBook_V5.docx` | Backend-side path to V5 DOCX |
