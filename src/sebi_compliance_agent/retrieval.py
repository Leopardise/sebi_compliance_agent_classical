from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set

import numpy as np
from rapidfuzz import fuzz

from .models import Clause

try:
    from rank_bm25 import BM25Okapi
except Exception:
    BM25Okapi = None


def _tokenize(text: str) -> List[str]:
    return [t.strip().lower() for t in text.replace("\n", " ").split() if t.strip()]


@dataclass
class RetrievalResult:
    clause_id: str
    score: float
    bm25_score: float
    dense_score: float
    fuzzy_score: float
    heading: str
    page_start: Optional[int]
    page_end: Optional[int]
    text_preview: str


class HybridRetriever:
    def __init__(
        self,
        clauses: Sequence[Clause],
        use_dense: bool = False,
        dense_model_name: str = "BAAI/bge-small-en-v1.5",
        bm25_weight: float = 0.60,
        dense_weight: float = 0.25,
        fuzzy_weight: float = 0.15,
    ) -> None:
        self.clauses = list(clauses)
        self.clause_by_id: Dict[str, Clause] = {c.clause_id: c for c in self.clauses}
        self.bm25_weight = bm25_weight
        self.dense_weight = dense_weight
        self.fuzzy_weight = fuzzy_weight

        self.corpus = [f"{c.heading}\n{c.text}" for c in self.clauses]
        self.has_corpus = len(self.corpus) > 0

        self.bm25 = None
        if self.has_corpus and BM25Okapi is not None:
            toks = [_tokenize(x) for x in self.corpus]
            if any(len(t) > 0 for t in toks):
                self.bm25 = BM25Okapi(toks)

        self.use_dense = False
        self.embedding_model = None
        self.faiss_index = None

        if use_dense and self.has_corpus:
            try:
                from sentence_transformers import SentenceTransformer
                import faiss

                self.embedding_model = SentenceTransformer(dense_model_name)
                mat = self.embedding_model.encode(
                    self.corpus,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                ).astype("float32")

                index = faiss.IndexFlatIP(mat.shape[1])
                index.add(mat)

                self.faiss_index = index
                self.use_dense = True
            except Exception:
                self.use_dense = False

    @staticmethod
    def _normalize_scores(scores: np.ndarray) -> np.ndarray:
        if scores.size == 0:
            return scores
        mn, mx = float(scores.min()), float(scores.max())
        if abs(mx - mn) < 1e-12:
            return np.ones_like(scores) * 0.5
        return (scores - mn) / (mx - mn)

    def _dense_search(self, query: str, top_k: int) -> Dict[str, float]:
        if not self.use_dense or self.embedding_model is None or self.faiss_index is None:
            return {}

        q = self.embedding_model.encode(
            [query],
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype("float32")
        scores, idxs = self.faiss_index.search(q, top_k)
        out: Dict[str, float] = {}
        for score, idx in zip(scores[0], idxs[0]):
            if idx >= 0:
                out[self.clauses[idx].clause_id] = float(score)
        return out

    def retrieve(
        self,
        query: str,
        top_k: int = 8,
        candidate_clause_ids: Optional[Set[str]] = None,
    ) -> List[RetrievalResult]:
        if not self.has_corpus:
            return []

        allowed_mask = np.ones(len(self.clauses), dtype=bool)
        if candidate_clause_ids is not None:
            allowed_mask = np.array([c.clause_id in candidate_clause_ids for c in self.clauses], dtype=bool)
            if not allowed_mask.any():
                return []

        if self.bm25 is not None:
            bm25_raw = np.array(self.bm25.get_scores(_tokenize(query)), dtype=float)
        else:
            bm25_raw = np.zeros(len(self.clauses), dtype=float)
        bm25_raw[~allowed_mask] = -1e9
        bm25_norm = self._normalize_scores(bm25_raw)

        dense_raw = np.zeros(len(self.clauses), dtype=float)
        dense_scores = self._dense_search(query, max(top_k * 5, 30))
        if dense_scores:
            for i, clause in enumerate(self.clauses):
                dense_raw[i] = dense_scores.get(clause.clause_id, 0.0)
        dense_raw[~allowed_mask] = -1e9
        dense_norm = self._normalize_scores(dense_raw)

        fuzzy_raw = np.array(
            [
                max(
                    fuzz.partial_ratio(query.lower(), clause.heading.lower()) / 100.0,
                    fuzz.partial_ratio(query.lower(), clause.text[:500].lower()) / 100.0,
                )
                for clause in self.clauses
            ],
            dtype=float,
        )
        fuzzy_raw[~allowed_mask] = -1e9
        fuzzy_norm = self._normalize_scores(fuzzy_raw)

        final_scores = (
            self.bm25_weight * bm25_norm
            + self.dense_weight * dense_norm
            + self.fuzzy_weight * fuzzy_norm
        )

        order = np.argsort(-final_scores)
        results: List[RetrievalResult] = []
        for idx in order:
            if len(results) >= top_k:
                break
            if not allowed_mask[int(idx)]:
                continue
            clause = self.clauses[int(idx)]
            results.append(
                RetrievalResult(
                    clause_id=clause.clause_id,
                    score=float(final_scores[idx]),
                    bm25_score=float(bm25_norm[idx]),
                    dense_score=float(dense_norm[idx]),
                    fuzzy_score=float(fuzzy_norm[idx]),
                    heading=clause.heading,
                    page_start=clause.page_start,
                    page_end=clause.page_end,
                    text_preview=clause.text[:220].replace("\n", " "),
                )
            )
        return results