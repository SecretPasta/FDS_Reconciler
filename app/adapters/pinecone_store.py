from __future__ import annotations

import asyncio
import logging
from typing import Any

from pinecone import Pinecone, ServerlessSpec

from app.config import PineconeSettings
from app.ports.vector_store import QueryResult, VectorRecord

logger = logging.getLogger(__name__)

_UPSERT_BATCH = 100


class PineconeStore:
    def __init__(self, settings: PineconeSettings, dimension: int) -> None:
        self._pc = Pinecone(api_key=settings.api_key.get_secret_value())
        self._settings = settings
        self._dimension = dimension
        self._index: Any = None
        self._lock = asyncio.Lock()

    # ── lazy init ────────────────────────────────────────────────────────────

    async def _ensure_index(self) -> Any:
        if self._index is not None:
            return self._index
        async with self._lock:
            if self._index is not None:  # re-check after acquiring
                return self._index
            self._index = await asyncio.to_thread(self._init_index)
        return self._index

    def _init_index(self) -> Any:
        existing = {i.name for i in self._pc.list_indexes()}
        if self._settings.index_name not in existing:
            logger.info("Creating Pinecone index '%s'", self._settings.index_name)
            self._pc.create_index(
                name=self._settings.index_name,
                dimension=self._dimension,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud=self._settings.cloud,
                    region=self._settings.region,
                ),
            )
        return self._pc.Index(self._settings.index_name)

    # ── VectorStore protocol ─────────────────────────────────────────────────

    async def upsert(self, vectors: list[VectorRecord]) -> None:
        index = await self._ensure_index()
        for i in range(0, len(vectors), _UPSERT_BATCH):
            batch = [
                {"id": v["id"], "values": v["values"], "metadata": v["metadata"]}
                for v in vectors[i : i + _UPSERT_BATCH]
            ]
            await asyncio.to_thread(
                index.upsert,
                vectors=batch,
                namespace=self._settings.namespace,
            )

    async def query(
        self,
        vector: list[float],
        top_k: int,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[QueryResult]:
        index = await self._ensure_index()
        kwargs: dict[str, Any] = {
            "vector": vector,
            "top_k": top_k,
            "namespace": self._settings.namespace,
            "include_metadata": True,
        }
        if metadata_filter is not None:
            kwargs["filter"] = metadata_filter
        result = await asyncio.to_thread(index.query, **kwargs)
        return [
            QueryResult(
                id=match.id,
                score=match.score,
                metadata=match.metadata or {},
            )
            for match in result.matches
        ]

    async def delete_all(self) -> None:
        index = await self._ensure_index()
        await asyncio.to_thread(
            index.delete,
            delete_all=True,
            namespace=self._settings.namespace,
        )
