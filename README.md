# FDS Reconciler

AI-powered system that compares two versions of a Functional Design Specification (PDF vs DOCX), detects MATCH / DIFF / MISSING sections, and answers questions about each document — including cross-document comparative questions.

---

## Overview

Given a PDF (version A) and a DOCX (version B) of an FDS, the system:

1. **Parses** both documents into structured sections (headings, prose, tables, bullets).
2. **Indexes** all chunks into Pinecone using Gemini embeddings.
3. **Aligns** sections deterministically (heading number + embedding similarity + Levenshtein).
4. **Compares** aligned pairs via Claude Sonnet, classifying each as MATCH, DIFF, or MISSING.
5. **Ranks** the top-10 most significant differences.
6. **Answers** natural-language questions via a chat endpoint (single-doc or cross-doc).

---

## Setup

### Native (uv)

```bash
# Install uv if needed
pip install uv

# Create venv and install deps
uv sync

# Copy and fill in secrets
cp .env.example .env

# Run the API server
uv run uvicorn app.api.main:app --reload
```

### Docker

```bash
docker build -t fds-reconciler .
docker run --env-file .env -p 8000:8000 fds-reconciler
```

---

## Architecture

The project follows a **hexagonal architecture**:

```
app/
├── domain/       # Pure Pydantic models — no I/O
├── ports/        # Protocol interfaces (LLMClient, EmbedderClient, VectorStore)
├── adapters/     # Concrete implementations of each port
├── parsing/      # PDF + DOCX → Section objects
├── indexing/     # Chunking + Pinecone upsert
├── comparison/   # LangGraph pipeline (align → judge → rank)
├── chat/         # RAG query handler
├── prompts/      # All LLM prompt strings
└── api/          # FastAPI routers and dependency wiring
```

Pipelines accept **ports (protocols)**, never concrete adapter types. `app/deps.py` is the single wiring point.

---

## Cross-Document Retrieval

For cross-document questions, the chat handler performs **dual retrieval**: top-4 chunks from document A and top-4 chunks from document B (each with an explicit `doc_id` filter). The Gemini Flash model synthesizes both context blocks, labeled:

```
## From V0 (PDF)
...

## From V5 (DOCX)
...
```

Citations use the format: `filename · §section · page N`

---

## Model Choices

| Task | Model | Reason |
|---|---|---|
| Comparison judging | Claude Sonnet 4.6 | Strong instruction-following for structured verdicts |
| Missing-section explanation | Claude Sonnet 4.6 | Detailed prose generation |
| Top-10 ranking | Claude Sonnet 4.6 | Reasoning over full result set |
| Chat synthesis | Gemini 2.5 Flash | Fast, long-context, grounded summarization |
| Embeddings | gemini-embedding-001 (768d) | Matryoshka, task-type aware, single provider |

---

## Limitations

- Designed for ~50-page documents; very large FDSs may hit Pinecone metadata size limits.
- Table comparison is structural (text diff), not semantic — reformatted tables may show false DIFFs.
- Chat answers are constrained to indexed context; questions requiring external knowledge will return `insufficient_context: true`.
- Alignment relies on consistent heading numbering; unnumbered documents fall back to embedding-only matching (lower precision).
- No persistent session storage — each request is stateless.