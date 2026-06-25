"""Parse both FDS documents, index them into Pinecone, and cache ParsedDoc JSON."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from app.domain.section import ParsedDoc

# Resolve project root so the script works from any working directory
_ROOT = Path(__file__).resolve().parent.parent
_SAMPLES = _ROOT / "samples"
_CACHE = _ROOT / ".cache"
_CACHE_FILE = _CACHE / "parsed_docs.json"

_PDF  = _SAMPLES / "FDS_PriceBook_V0.pdf"
_DOCX = _SAMPLES / "FDS_PriceBook_V5.docx"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    from app.adapters.gemini_embedder import GeminiEmbedder
    from app.adapters.pinecone_store import PineconeStore
    from app.config import get_settings
    from app.indexing.indexer import Indexer
    from app.parsing.docx_parser import parse_docx
    from app.parsing.pdf_parser import parse_pdf

    for path in (_PDF, _DOCX):
        if not path.exists():
            logger.error("Missing sample file: %s", path)
            sys.exit(1)

    # ── Parse ────────────────────────────────────────────────────────────────
    logger.info("Parsing %s", _PDF.name)
    doc_a = parse_pdf(_PDF, doc_id="A")
    logger.info("  %d sections", len(doc_a.sections))

    logger.info("Parsing %s", _DOCX.name)
    doc_b = parse_docx(_DOCX, doc_id="B")
    logger.info("  %d sections", len(doc_b.sections))

    # ── Cache parsed docs ────────────────────────────────────────────────────
    _CACHE.mkdir(exist_ok=True)
    _CACHE_FILE.write_text(
        json.dumps(
            {"A": doc_a.model_dump(mode="json"), "B": doc_b.model_dump(mode="json")},
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("Cached parsed docs → %s", _CACHE_FILE)

    # ── Index ────────────────────────────────────────────────────────────────
    settings = get_settings()
    embedder = GeminiEmbedder(settings.gemini)
    store    = PineconeStore(settings.pinecone, dimension=settings.gemini.embed_dimensions)
    indexer  = Indexer(embedder=embedder, store=store, chunking=settings.chunking)

    logger.info("Indexing doc A (PDF) …")
    await indexer.index_doc(doc_a)

    logger.info("Indexing doc B (DOCX) …")
    await indexer.index_doc(doc_b)

    logger.info("Done — both documents indexed.")


def load_cached_docs() -> tuple[ParsedDoc, ParsedDoc]:
    """Return (doc_a, doc_b) from the JSON cache written by this script."""
    if not _CACHE_FILE.exists():
        raise FileNotFoundError(f"Cache not found — run scripts/index_docs.py first ({_CACHE_FILE})")
    data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    return ParsedDoc.model_validate(data["A"]), ParsedDoc.model_validate(data["B"])


if __name__ == "__main__":
    asyncio.run(main())