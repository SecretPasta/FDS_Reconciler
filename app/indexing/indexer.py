from __future__ import annotations

import logging

from app.config import ChunkingSettings
from app.domain.section import ParsedDoc
from app.indexing.chunker import chunk_section
from app.ports.embedder import EmbedderClient
from app.ports.vector_store import VectorRecord, VectorStore

logger = logging.getLogger(__name__)


class Indexer:
    def __init__(
        self,
        embedder: EmbedderClient,
        store: VectorStore,
        chunking: ChunkingSettings,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._chunking = chunking

    async def index_doc(self, doc: ParsedDoc) -> None:
        chunks = [
            chunk
            for section in doc.sections
            for chunk in chunk_section(section, self._chunking)
        ]
        if not chunks:
            logger.warning("No chunks produced for doc '%s'", doc.doc_id)
            return

        logger.info("Embedding %d chunks for doc '%s'", len(chunks), doc.doc_id)
        vectors = await self._embedder.embed_documents([c.text for c in chunks])

        records: list[VectorRecord] = [
            VectorRecord(id=c.id, values=v, metadata=c.index_metadata())
            for c, v in zip(chunks, vectors)
        ]

        logger.info("Upserting %d vectors for doc '%s'", len(records), doc.doc_id)
        await self._store.upsert(records)