# FDS Reconciler

AI-powered system that compares two versions of a Functional Design Specification (PDF vs DOCX), detects MATCH / DIFF / MISSING sections, and answers questions about each document — including cross-document comparative questions.

---

## Quick start

### 1. Configure secrets

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, GEMINI_API_KEY, PINECONE_API_KEY
```

### 2. Run with Docker Compose

```bash
docker compose up --build
```

The API is available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### 3. Run natively (uv)

```bash
uv sync
uv run uvicorn app.main:app --reload
```

---

## Endpoints

### Compare two documents

Parses, indexes, aligns, and judges both documents. Returns the full diff result and a top-10 executive summary. Place your files anywhere accessible to the container (or mount them via the volume).

```bash
curl -X POST http://localhost:8000/compare \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_path":  "/app/samples/FDS_PriceBook_V0.pdf",
    "docx_path": "/app/samples/FDS_PriceBook_V5.docx"
  }'
```

### Get cached executive summary

Returns the top-10 changes from the most recent `/compare` run without re-running the pipeline.

```bash
curl http://localhost:8000/summary
```

### Chat — single document

Ask a question scoped to one document. `doc_id` is `"A"` (PDF) or `"B"` (DOCX).

```bash
curl -X POST http://localhost:8000/chat/single \
  -H "Content-Type: application/json" \
  -d '{
    "query":  "What are the three processing stages described in section 3.1?",
    "doc_id": "A"
  }'
```

### Chat — cross-document comparison

Ask a comparative question across both documents. The model labels each claim with its source.

```bash
curl -X POST http://localhost:8000/chat/cross \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How did the pricing calculation logic change between V0 and V5?"
  }'
```

**Response shape (all chat endpoints):**

```json
{
  "answer": "The pricing model changed from flat-rate to tiered. [FDS_V5.docx · §3.2]",
  "citations": ["FDS_V0.pdf · §3.2 · page 5", "FDS_V5.docx · §3.2"],
  "insufficient_context": false
}
```

---

## Tests

```bash
# All unit + adapter tests (~2 s)
uv run pytest

# Single file
uv run pytest tests/unit/test_aligner.py -v

# Integration tests (requires real .env and sample files)
uv run pytest -m integration
```

---

## Architecture

The project follows a **hexagonal architecture**:

```
app/
├── domain/       # Pure Pydantic models — no I/O
├── ports/        # Protocol interfaces (LLMClient, EmbedderClient, VectorStore)
├── adapters/     # Concrete implementations (Claude, Gemini, Pinecone)
├── parsing/      # PDF + DOCX → Section objects
├── indexing/     # Chunking + Pinecone upsert
├── comparison/   # LangGraph pipeline: align → judge → explain → rank
├── chat/         # LangGraph RAG pipeline: embed → retrieve → check → synthesize
├── prompts/      # All LLM prompt strings
├── api/          # FastAPI routers and schemas
└── deps.py       # Single DI wiring point (@lru_cache singletons)
```

Pipelines accept **ports (protocols)**, never concrete adapter types.

---

## Cross-document retrieval

For comparative questions, the chat pipeline performs **dual retrieval**: top-4 chunks from document A and top-4 from document B via parallel Pinecone queries. Gemini Flash synthesizes both context blocks, labeled:

```
## From V0 (PDF)
[FDS_V0.pdf · §3.2 · page 5]
Base price is determined by tier and volume.

## From V5 (DOCX)
[FDS_V5.docx · §3.2]
Base price is determined by tier and volume. Discounts now apply.
```

If both sides return low-relevance results a single unfiltered fallback query is attempted before the response is marked `insufficient_context: true`.

---

## Model choices

| Task | Model | Reason |
|---|---|---|
| Comparison judging | Claude Sonnet 4.6 | Strong instruction-following for structured verdicts |
| Missing-section explanation | Claude Sonnet 4.6 | Detailed prose generation |
| Top-10 ranking | Claude Sonnet 4.6 | Reasoning over full result set |
| Chat synthesis | Gemini 2.5 Flash | Fast, long-context, grounded summarization |
| Embeddings | gemini-embedding-001 (768d) | Matryoshka, task-type aware |

---

## Limitations

- Designed for ~50-page documents; very large FDSs may hit Pinecone metadata size limits.
- Table comparison is structural (text diff), not semantic — reformatted tables may show false DIFFs.
- Chat is constrained to indexed context; questions requiring external knowledge return `insufficient_context: true`.
- Alignment relies on consistent heading numbering; unnumbered documents fall back to embedding-only matching.
- The `/compare` result is cached in-process; restart the container to clear it.
