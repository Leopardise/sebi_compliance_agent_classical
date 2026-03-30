from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class Reference:
    raw_text: str
    target_type: str
    normalized_target: str
    title_hint: Optional[str] = None
    citation_hint: Optional[str] = None
    cited_page_numbers: List[int] = field(default_factory=list)
    source_clause_id: Optional[str] = None
    source_page_start: Optional[int] = None
    source_page_end: Optional[int] = None
    resolved_node_id: Optional[str] = None
    confidence: float = 0.0


@dataclass
class Obligation:
    subject: str
    action: str
    object_text: str
    condition: Optional[str] = None
    deadline: Optional[str] = None
    frequency: Optional[str] = None
    applicability: List[str] = field(default_factory=list)
    evidence_hints: List[str] = field(default_factory=list)
    source_clause_id: Optional[str] = None
    source_page_start: Optional[int] = None
    source_page_end: Optional[int] = None
    confidence: float = 0.0


@dataclass
class Clause:
    clause_id: str
    document_id: str
    heading: str
    text: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    references: List[Reference] = field(default_factory=list)
    obligations: List[Obligation] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Document:
    document_id: str
    title: str
    doc_type: str
    date: Optional[str]
    issuer: Optional[str]
    source_path: str
    text: str
    page_texts: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    clauses: List[Clause] = field(default_factory=list)


@dataclass
class Answer:
    question: str
    conclusion: str
    rationale: List[str]
    cited_clause_ids: List[str]
    reference_chain: List[str]
    confidence: str
    gaps: List[str]

    def to_dict(self) -> Dict:
        return asdict(self)