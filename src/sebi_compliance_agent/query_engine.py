from __future__ import annotations

import re
from typing import List, Optional, Set

from .graph_store import ComplianceGraph
from .models import Answer, Clause
from .retrieval import HybridRetriever


class QueryEngine:
    def __init__(self, graph: ComplianceGraph, retriever: Optional[HybridRetriever] = None) -> None:
        self.graph = graph
        self.retriever = retriever

    @staticmethod
    def _norm(s: str) -> str:
        return " ".join(s.lower().strip().split())

    def _detect_target_documents(self, question: str) -> Set[str]:
        q = self._norm(question)
        matched: Set[str] = set()

        # exact synthetic circular targeting
        m = re.search(r"synthetic circular\s+(\d+)", q)
        if m:
            wanted = m.group(1)
            for doc_id, doc in self.graph.documents.items():
                title = self._norm(doc.title)
                if f"synthetic circular {wanted}" in title:
                    matched.add(doc_id)
            if matched:
                return matched

        for doc_id, doc in self.graph.documents.items():
            title = self._norm(doc.title)
            if title and (title in q or q in title):
                matched.add(doc_id)

        return matched

    def _candidate_clause_ids_for_docs(self, doc_ids: Set[str]) -> Set[str]:
        out: Set[str] = set()
        for doc_id in doc_ids:
            doc = self.graph.documents.get(doc_id)
            if not doc:
                continue
            for clause in doc.clauses:
                out.add(clause.clause_id)
        return out

    def answer(self, question: str, top_k: int = 5) -> Answer:
        target_docs = self._detect_target_documents(question)
        candidate_clause_ids = self._candidate_clause_ids_for_docs(target_docs) if target_docs else None

        if self.retriever is not None:
            retrieved = self.retriever.retrieve(question, top_k=top_k, candidate_clause_ids=candidate_clause_ids)
            clauses = [self.graph.clauses[r.clause_id] for r in retrieved if r.clause_id in self.graph.clauses]
        else:
            clauses = self.graph.search_clauses(question, top_k=top_k)

        if not clauses:
            return Answer(
                question=question,
                conclusion="No high-confidence answer found.",
                rationale=["No matching clauses were retrieved from the indexed corpus."],
                cited_clause_ids=[],
                reference_chain=[],
                confidence="low",
                gaps=["Relevant document may not be ingested yet."],
            )

        q_norm = self._norm(question)
        ask_references = "reference" in q_norm or "references" in q_norm or "cites" in q_norm

        cited_ids = [clause.clause_id for clause in clauses]
        rationale: List[str] = []
        reference_chain: List[str] = []
        gaps: List[str] = []

        if ask_references:
            seen = set()
            found_any = False
            for clause in clauses:
                for ref in clause.references:
                    key = (ref.raw_text, ref.source_page_start, ref.source_page_end)
                    if key in seen:
                        continue
                    seen.add(key)
                    found_any = True
                    page_span = (
                        f"page {ref.source_page_start}"
                        if ref.source_page_start == ref.source_page_end
                        else f"pages {ref.source_page_start}-{ref.source_page_end}"
                    )
                    resolved = f" -> {ref.resolved_node_id}" if ref.resolved_node_id else ""
                    rationale.append(f"Reference on {page_span}: {ref.raw_text}{resolved}")

            if not found_any:
                rationale.append("Relevant clauses were retrieved, but no explicit references were extracted from them.")

            for clause in clauses:
                for relation, target in self.graph.related_nodes(clause.clause_id):
                    if relation == "refers_to":
                        reference_chain.append(f"{clause.clause_id} -> {target}")
                    elif relation == "refers_to_unresolved":
                        gaps.append(f"Unresolved reference from {clause.clause_id}: {target}")

            return Answer(
                question=question,
                conclusion="Extracted references from the most relevant clauses.",
                rationale=rationale,
                cited_clause_ids=cited_ids,
                reference_chain=reference_chain,
                confidence="medium" if rationale else "low",
                gaps=gaps,
            )

        obligation_count = 0
        for clause in clauses:
            if clause.obligations:
                obligation_count += len(clause.obligations)
                rationale.append(self._summarize_clause(clause))
            else:
                rationale.append(f"{clause.heading} [pages {clause.page_start}-{clause.page_end}]: relevant text found but no explicit obligation extracted.")

            for relation, target in self.graph.related_nodes(clause.clause_id):
                if relation == "refers_to":
                    reference_chain.append(f"{clause.clause_id} -> {target}")
                elif relation == "refers_to_unresolved":
                    gaps.append(f"Unresolved reference from {clause.clause_id}: {target}")

        posture = "Likely applicable obligations identified." if obligation_count > 0 else "Relevant clauses were found, but no explicit structured obligation was extracted."
        confidence = "medium" if obligation_count > 0 else "low"

        return Answer(
            question=question,
            conclusion=posture,
            rationale=rationale,
            cited_clause_ids=cited_ids,
            reference_chain=reference_chain,
            confidence=confidence,
            gaps=gaps,
        )

    @staticmethod
    def _summarize_clause(clause: Clause) -> str:
        page_span = f"page {clause.page_start}" if clause.page_start == clause.page_end else f"pages {clause.page_start}-{clause.page_end}"
        if clause.obligations:
            obligation = clause.obligations[0]
            deadline = f" ({obligation.deadline})" if obligation.deadline else ""
            return f"{clause.heading} [{page_span}]: {obligation.subject} should {obligation.action} {obligation.object_text}{deadline}"
        snippet = clause.text.strip().replace("\n", " ")
        return f"{clause.heading} [{page_span}]: {snippet[:180]}"