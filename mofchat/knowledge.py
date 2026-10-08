"""Retrieval over the knowledge index (curated notes + MOF papers)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from . import _faiss  # noqa: F401
from .config import KNOWLEDGE_INDEX_DIR, TEXT_EMBEDDING_MODEL

RELEVANCE_THRESHOLD = 0.30   # cosine similarity below which a question is treated as off-topic


@dataclass
class Snippet:
    text: str
    source: str
    score: float
    page: int | None = None
    section: str | None = None

    def citation(self) -> str:
        if self.page:
            return f"{self.source}, p. {self.page}"
        return f"{self.source}" + (f" - {self.section}" if self.section else "")


@lru_cache(maxsize=1)
def _store():
    from langchain_community.vectorstores import FAISS
    from langchain_community.vectorstores.utils import DistanceStrategy
    from langchain_huggingface import HuggingFaceEmbeddings

    if not (KNOWLEDGE_INDEX_DIR / "index.faiss").exists():
        return None
    emb = HuggingFaceEmbeddings(model_name=TEXT_EMBEDDING_MODEL, encode_kwargs={"normalize_embeddings": True})
    return FAISS.load_local(str(KNOWLEDGE_INDEX_DIR), emb, allow_dangerous_deserialization=True,
                            distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT)


def available() -> bool:
    return _store() is not None


def search(query: str, k: int = 4) -> list[Snippet]:
    store = _store()
    if store is None:
        return []
    hits = store.similarity_search_with_score(query, k=k)
    return [Snippet(d.page_content, d.metadata.get("source", "?"), float(s), d.metadata.get("page"),
                    d.metadata.get("section")) for d, s in hits]


def is_relevant(snippets: list[Snippet]) -> bool:
    return bool(snippets) and snippets[0].score >= RELEVANCE_THRESHOLD
