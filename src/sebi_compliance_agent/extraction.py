from __future__ import annotations

import re
from typing import List, Optional

from .models import Clause, Obligation, Reference
import os

FULL_REFERENCE_PATTERNS = [
    (
        "full_read_with_clause_title",
        re.compile(
            r'((?:This\s+Circular|This\s+Master\s+Circular|This\s+document)\s+'
            r'(?:shall|should)\s+be\s+read\s+with\s+'
            r'(?:Clause|Para|Paragraph)\s+\d+(?:\.\d+)*\s+of\s+the\s+'
            r'[A-Z][A-Za-z0-9,&()\/\-\s]+?(?:Act|Rules|Regulations|Guidelines|Circular)(?:,?\s*\d{4})?)',
            re.IGNORECASE,
        ),
        0.98,
    ),
    (
        "full_clause_of_title",
        re.compile(
            r'((?:Clause|Para|Paragraph)\s+\d+(?:\.\d+)*\s+of\s+the\s+'
            r'[A-Z][A-Za-z0-9,&()\/\-\s]+?(?:Act|Rules|Regulations|Guidelines|Circular)(?:,?\s*\d{4})?)',
            re.IGNORECASE,
        ),
        0.97,
    ),
    (
        "full_regulation_of_title",
        re.compile(
            r'((?:Regulation|Reg\.)\s+\d+(?:\.\d+)*\s+of\s+the\s+'
            r'[A-Z][A-Za-z0-9,&()\/\-\s]+?(?:Act|Rules|Regulations)(?:,?\s*\d{4})?)',
            re.IGNORECASE,
        ),
        0.96,
    ),
    (
        "full_section_of_title",
        re.compile(
            r'((?:Section|Sec\.)\s+\d+[A-Za-z0-9()\-\.]*\s+of\s+the\s+'
            r'[A-Z][A-Za-z0-9,&()\/\-\s]+?(?:Act|Rules|Regulations)(?:,?\s*\d{4})?)',
            re.IGNORECASE,
        ),
        0.96,
    ),
]

TITLE_ONLY_PATTERNS = [
    ("act_title", re.compile(r'([A-Z][A-Za-z,&()\- ]+? Act,? \d{4})'), 0.90),
    ("rules_title", re.compile(r'([A-Z][A-Za-z,&()\- ]+? Rules,? \d{4})'), 0.88),
    ("regulations_title", re.compile(r'([A-Z][A-Za-z,&()\- ]+? Regulations,? \d{4})'), 0.90),
    ("master_circular_title", re.compile(r'(Master Circular(?:\s+for|\s+on)?[^.;\n]{0,160})', re.IGNORECASE), 0.90),
    ("guideline_title", re.compile(r'([A-Z][A-Za-z,&()\- ]+? Guidelines(?:,?\s*\d{4})?)'), 0.86),
    ("circular_title", re.compile(r'([A-Z][A-Za-z,&()\- ]+? Circular(?:,?\s*\d{4})?)'), 0.84),
]

MANDATORY_PATTERNS = [
    "shall", "must", "required to", "is required to", "ensure", "submit", "maintain",
    "disclose", "furnish", "report", "provide", "appoint", "verify", "file", "comply with"
]

APPLICABILITY_HINTS = {
    "bank": "bank",
    "listed entity": "listed_entity",
    "intermediary": "intermediary",
    "issuer": "issuer",
    "mutual fund": "mutual_fund",
    "asset management company": "amc",
    "custodian": "custodian",
    "depository": "depository",
    "stock exchange": "stock_exchange",
    "investment adviser": "investment_adviser",
    "research analyst": "research_analyst",
}

EVIDENCE_HINTS = [
    "policy", "report", "filing", "disclosure", "register", "log", "board approval",
    "certificate", "agreement", "record", "internal controls", "audit trail", "intimation"
]

DEADLINE_PATTERNS = [
    r'within\s+\d+\s+(?:calendar\s+)?days',
    r'not\s+later\s+than\s+[^.;]+',
    r'on\s+or\s+before\s+[^.;]+',
    r'quarterly',
    r'monthly',
    r'annually',
    r'half-yearly',
    r'immediately',
    r'promptly',
    r'forthwith',
]

PAGE_NO_RE = re.compile(r'(?:page|pg\.)\s*(\d+)', re.IGNORECASE)
CIRCULAR_ID_RE = re.compile(r'(?:SEBI/)?[A-Z][A-Z0-9/()\-.]{6,}')
CLAUSE_NUM_RE = re.compile(r'(?:Clause|Para|Paragraph)\s+(\d+(?:\.\d+)*)', re.IGNORECASE)


def normalize_reference(text: str) -> str:
    text = text.strip().strip(",:;.-")
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def sentence_split(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r'(?<=[.;])\s+', text) if s.strip()]


def detect_applicability(text: str) -> List[str]:
    lowered = text.lower()
    return [mapped for phrase, mapped in APPLICABILITY_HINTS.items() if phrase in lowered]


def detect_evidence_hints(text: str) -> List[str]:
    lowered = text.lower()
    return [hint for hint in EVIDENCE_HINTS if hint in lowered]


def extract_deadline(text: str) -> Optional[str]:
    for pattern in DEADLINE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return None


def extract_subject_action_object(sentence: str) -> tuple[str, str, str]:
    lowered = sentence.lower()
    subject = "regulated entity"
    for phrase in APPLICABILITY_HINTS:
        if phrase in lowered:
            subject = phrase
            break

    action = "comply"
    for verb in ["submit", "maintain", "disclose", "furnish", "appoint", "report", "ensure", "notify", "keep", "file", "provide", "verify"]:
        if re.search(rf"\b{verb}\b", lowered):
            action = verb
            break

    object_text = sentence
    for marker in ["shall", "must", "required to", "is required to", "ensure that"]:
        idx = lowered.find(marker)
        if idx != -1:
            object_text = sentence[idx + len(marker):].strip(" :,-")
            break

    return subject, action, object_text


def _extract_cited_pages(raw_text: str) -> List[int]:
    return [int(m.group(1)) for m in PAGE_NO_RE.finditer(raw_text)]


def _citation_hint(raw_text: str) -> Optional[str]:
    m = CIRCULAR_ID_RE.search(raw_text)
    return m.group(0) if m else None


def _extract_title_hint(raw_text: str) -> Optional[str]:
    x = raw_text.strip(" .;,:")
    x = re.sub(
        r'^(?:This\s+Circular|This\s+Master\s+Circular|This\s+document)\s+(?:shall|should)\s+be\s+read\s+with\s+',
        '',
        x,
        flags=re.IGNORECASE,
    )
    x = re.sub(r'^(?:Clause|Para|Paragraph)\s+\d+(?:\.\d+)*\s+of\s+the\s+', '', x, flags=re.IGNORECASE)
    x = re.sub(r'^(?:Regulation|Reg\.)\s+\d+(?:\.\d+)*\s+of\s+the\s+', '', x, flags=re.IGNORECASE)
    x = re.sub(r'^(?:Section|Sec\.)\s+\d+[A-Za-z0-9()\-\.]*\s+of\s+the\s+', '', x, flags=re.IGNORECASE)
    x = x.strip(" .;,:")
    return x[:220] if x else None


def _extract_clause_num(raw_text: str) -> Optional[str]:
    m = CLAUSE_NUM_RE.search(raw_text)
    return m.group(1) if m else None


def _detect_target_type(raw_text: str, fallback_type: str) -> str:
    lowered = raw_text.lower()
    if "master circular" in lowered:
        return "master_circular"
    if "regulations" in lowered or "regulation" in lowered:
        return "regulation"
    if "section" in lowered or "sec." in lowered:
        return "section"
    if "clause" in lowered or "para" in lowered or "paragraph" in lowered:
        return "clause"
    if " act" in lowered or "act," in lowered:
        return "act"
    if "rules" in lowered:
        return "rules"
    if "guidelines" in lowered:
        return "guideline"
    if "circular" in lowered:
        return "circular"
    return fallback_type


def _dedup_key(title_hint: str, clause_num: Optional[str], clause_id: str) -> tuple:
    return (
        normalize_reference(title_hint),
        clause_num or "",
        clause_id,
    )


def extract_references(clause: Clause) -> List[Reference]:
    refs: List[Reference] = []
    mode = os.environ.get("SEBI_EXTRACTOR_MODE", "balanced").lower()
    seen = set()
    text = clause.text

    for fallback_type, pattern, base_conf in FULL_REFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(1).strip()
            title_hint = _extract_title_hint(raw) or ""
            clause_num = _extract_clause_num(raw)
            key = _dedup_key(title_hint, clause_num, clause.clause_id)
            if key in seen:
                continue
            seen.add(key)

            refs.append(
                Reference(
                    raw_text=raw,
                    target_type=_detect_target_type(raw, fallback_type),
                    normalized_target=normalize_reference(raw),
                    title_hint=title_hint,
                    citation_hint=_citation_hint(raw),
                    cited_page_numbers=_extract_cited_pages(raw),
                    source_clause_id=clause.clause_id,
                    source_page_start=clause.page_start,
                    source_page_end=clause.page_end,
                    confidence=base_conf,
                )
            )

    if refs and mode == "strict":
        return refs

    if refs and mode == "balanced":
        return refs

    for fallback_type, pattern, base_conf in TITLE_ONLY_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(1).strip()
            title_hint = _extract_title_hint(raw) or raw
            key = _dedup_key(title_hint, None, clause.clause_id)
            if key in seen:
                continue
            seen.add(key)

            refs.append(
                Reference(
                    raw_text=raw,
                    target_type=_detect_target_type(raw, fallback_type),
                    normalized_target=normalize_reference(raw),
                    title_hint=title_hint,
                    citation_hint=_citation_hint(raw),
                    cited_page_numbers=_extract_cited_pages(raw),
                    source_clause_id=clause.clause_id,
                    source_page_start=clause.page_start,
                    source_page_end=clause.page_end,
                    confidence=base_conf,
                )
            )

    return refs


def extract_obligations(clause: Clause) -> List[Obligation]:
    obligations: List[Obligation] = []
    for sentence in sentence_split(clause.text):
        lowered = sentence.lower()
        if not any(p in lowered for p in MANDATORY_PATTERNS):
            continue

        subject, action, object_text = extract_subject_action_object(sentence)
        obligations.append(
            Obligation(
                subject=subject,
                action=action,
                object_text=object_text,
                condition=None,
                deadline=extract_deadline(sentence),
                frequency=(
                    "quarterly" if "quarterly" in lowered else
                    "monthly" if "monthly" in lowered else
                    "annually" if "annually" in lowered else
                    "half-yearly" if "half-yearly" in lowered else None
                ),
                applicability=detect_applicability(sentence),
                evidence_hints=detect_evidence_hints(sentence),
                source_clause_id=clause.clause_id,
                source_page_start=clause.page_start,
                source_page_end=clause.page_end,
                confidence=0.85 if len(object_text) > 20 else 0.70,
            )
        )
    return obligations


def enrich_clause(clause: Clause) -> Clause:
    clause.references = extract_references(clause)
    clause.obligations = extract_obligations(clause)
    return clause