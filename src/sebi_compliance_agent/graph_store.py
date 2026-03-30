from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import DefaultDict, Dict, List, Optional

from .models import Clause, Document, Obligation, Reference


class ComplianceGraph:
    def __init__(self) -> None:
        self.documents: Dict[str, Document] = {}
        self.clauses: Dict[str, Clause] = {}
        self.obligations: Dict[str, Obligation] = {}
        self.edges: DefaultDict[str, List[tuple[str, str]]] = defaultdict(list)
        self.reverse_edges: DefaultDict[str, List[tuple[str, str]]] = defaultdict(list)
        self.reference_index: Dict[str, str] = {}

    def add_document(self, document: Document) -> None:
        self.documents[document.document_id] = document
        self._index_document_aliases(document)

        for clause in document.clauses:
            self.clauses[clause.clause_id] = clause
            self.add_edge(document.document_id, 'has_clause', clause.clause_id)

            for ref in clause.references:
                target = self.resolve_reference(ref)
                if target:
                    ref.resolved_node_id = target
                    self.add_edge(clause.clause_id, 'refers_to', target)
                else:
                    self.add_edge(clause.clause_id, 'refers_to_unresolved', ref.normalized_target)

            for idx, obligation in enumerate(clause.obligations):
                oid = f'{clause.clause_id}::obligation::{idx}'
                self.obligations[oid] = obligation
                self.add_edge(clause.clause_id, 'has_obligation', oid)
                for applicability in obligation.applicability:
                    self.add_edge(oid, 'applies_to', applicability)
                for evidence in obligation.evidence_hints:
                    self.add_edge(oid, 'evidenced_by_hint', evidence)

    def _index_document_aliases(self, document: Document) -> None:
        candidates = set()
        title = self._normalize(document.title)
        candidates.add(title)

        circular_no = document.metadata.get('circular_no', '')
        if circular_no:
            candidates.add(self._normalize(circular_no))

        candidates.add(self._normalize(re.sub(r'\bsebi\b', '', document.title, flags=re.IGNORECASE)))

        for cand in candidates:
            if cand:
                self.reference_index[cand] = document.document_id

    def add_edge(self, source: str, relation: str, target: str) -> None:
        self.edges[source].append((relation, target))
        self.reverse_edges[target].append((relation, source))

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r'[^a-z0-9/()\-. ]+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def resolve_reference(self, ref: Reference) -> Optional[str]:
        normalized_reference = self._normalize(ref.normalized_target)
        title_hint = self._normalize(ref.title_hint or '')
        citation_hint = self._normalize(ref.citation_hint or '')

        for key, value in self.reference_index.items():
            if normalized_reference == key or title_hint == key or citation_hint == key:
                return value
            if normalized_reference and (normalized_reference in key or key in normalized_reference):
                return value
            if title_hint and (title_hint in key or key in title_hint):
                return value
            if citation_hint and citation_hint in key:
                return value

        clause_num = self._extract_clause_number(normalized_reference)
        if clause_num:
            source_clause = self.clauses.get(ref.source_clause_id or '')
            if source_clause:
                source_doc_id = source_clause.document_id
                for clause in self.documents[source_doc_id].clauses:
                    if clause.metadata.get('clause_number', '').lower() == clause_num:
                        return clause.clause_id

            for clause in self.clauses.values():
                if clause.metadata.get('clause_number', '').lower() == clause_num:
                    return clause.clause_id

        best_score = 0.0
        best_doc_id: Optional[str] = None
        probe = title_hint or normalized_reference
        if probe:
            for key, value in self.reference_index.items():
                score = SequenceMatcher(a=probe, b=key).ratio()
                if score > best_score:
                    best_score, best_doc_id = score, value
            if best_score >= 0.86:
                return best_doc_id

        return None

    @staticmethod
    def _extract_clause_number(text: str) -> Optional[str]:
        m = re.search(r'(?:clause|para|paragraph)\s+(\d+(?:\.\d+)*)', text)
        return m.group(1).lower() if m else None

    def resolve_pending_references(self) -> None:
        for clause in self.clauses.values():
            kept = [(rel, tgt) for rel, tgt in self.edges.get(clause.clause_id, []) if rel not in {'refers_to', 'refers_to_unresolved'}]
            new_edges = []

            for ref in clause.references:
                if ref.resolved_node_id:
                    new_edges.append(('refers_to', ref.resolved_node_id))
                    continue
                target = self.resolve_reference(ref)
                if target:
                    ref.resolved_node_id = target
                    new_edges.append(('refers_to', target))
                else:
                    new_edges.append(('refers_to_unresolved', ref.normalized_target))

            self.edges[clause.clause_id] = kept + new_edges

    def related_nodes(self, node_id: str) -> List[tuple[str, str]]:
        return self.edges.get(node_id, [])

    def search_clauses(self, query: str, top_k: int = 5) -> List[Clause]:
        terms = [self._normalize(term) for term in query.split() if len(term) > 2]
        scored: List[tuple[float, Clause]] = []
        for clause in self.clauses.values():
            haystack = self._normalize(f'{clause.heading} {clause.text}')
            score = 0.0
            for term in terms:
                if term in haystack:
                    score += haystack.count(term)

            for obligation in clause.obligations:
                obligation_text = self._normalize(f'{obligation.subject} {obligation.action} {obligation.object_text}')
                for term in terms:
                    if term in obligation_text:
                        score += 2.0

            if score > 0:
                scored.append((score, clause))

        scored.sort(key=lambda x: (-x[0], x[1].clause_id))
        return [clause for _, clause in scored[:top_k]]

    def unresolved_references(self) -> List[str]:
        unresolved: List[str] = []
        for source, edges in self.edges.items():
            for relation, target in edges:
                if relation == 'refers_to_unresolved':
                    unresolved.append(f'{source} -> {target}')
        return unresolved

    def stats(self) -> Dict[str, int]:
        return {
            'documents': len(self.documents),
            'clauses': len(self.clauses),
            'obligations': len(self.obligations),
            'edges': sum(len(v) for v in self.edges.values()),
            'unresolved_references': len(self.unresolved_references()),
        }