from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .models import Clause, Document

DATE_RE = re.compile(
    r'(?:dated|date)\s*[:\-]?\s*('
    r'\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4}'
    r'|\d{1,2}\s+[A-Za-z]+\s+\d{4}'
    r'|[A-Za-z]+\s+\d{1,2},\s*\d{4}'
    r')',
    re.IGNORECASE,
)

CIRCULAR_NO_RE = re.compile(
    r'(?:circular\s+no\.?|reference\s+no\.?)\s*[:\-]?\s*([A-Z0-9/()\-.]+)',
    re.IGNORECASE,
)

# STRICT heading patterns only
NUMERIC_HEADING_RE = re.compile(
    r'^\s*(\d+(?:\.\d+)*)[.)]?\s+(.{1,160})\s*$'
)
ROMAN_HEADING_RE = re.compile(
    r'^\s*([IVXLCM]+)[.)]?\s+(.{1,160})\s*$',
    re.IGNORECASE,
)

ALLOWED_NAMED_HEADINGS = {
    "scope",
    "applicability",
    "definitions",
    "background",
    "objective",
    "obligations",
    "disclosures",
    "record keeping",
    "compliance",
    "reporting",
    "procedure",
    "effective date",
    "implementation",
    "annexure",
}


@dataclass
class RawText:
    text: str
    page_texts: List[str]


def _clean_page_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r'[\t\r]+', ' ', text)
    text = re.sub(r'[ ]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def read_text(path: Path) -> RawText:
    suffix = path.suffix.lower()

    if suffix in {".txt", ".md"}:
        text = _clean_page_text(path.read_text(encoding="utf-8"))
        return RawText(text=text, page_texts=[text])

    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Unsupported JSON shape in {path}")
        text = _clean_page_text(str(data.get("text", "")))
        return RawText(text=text, page_texts=[text])

    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        page_texts = [_clean_page_text(page.extract_text() or "") for page in reader.pages]
        return RawText(text="\n\n".join(page_texts), page_texts=page_texts)

    raise ValueError(f"Unsupported file type: {suffix}")


def infer_doc_type(text: str, path: Path) -> str:
    lowered = (text[:8000] + " " + path.name).lower()
    if "master circular" in lowered:
        return "master_circular"
    if "circular" in lowered:
        return "circular"
    if "regulation" in lowered or "regulations" in lowered:
        return "regulation"
    if "act" in lowered:
        return "act"
    if "guideline" in lowered:
        return "guideline"
    return "document"


def infer_title(text: str, path: Path) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s and len(s) >= 8:
            return s[:220]
    return path.stem


def infer_date(text: str) -> Optional[str]:
    m = DATE_RE.search(text[:12000])
    return m.group(1) if m else None


def infer_issuer(text: str) -> Optional[str]:
    lowered = text[:12000].lower()
    if "securities and exchange board of india" in lowered or "sebi" in lowered:
        return "SEBI"
    return None


def infer_circular_no(text: str) -> Optional[str]:
    m = CIRCULAR_NO_RE.search(text[:12000])
    return m.group(1).strip() if m else None


def make_document_id(path: Path, title: str) -> str:
    digest = hashlib.md5(f"{path.as_posix()}::{title}".encode("utf-8")).hexdigest()[:12]
    return f"doc_{digest}"


def _iter_lines_with_pages(doc: Document) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    if doc.page_texts:
        for idx, page_text in enumerate(doc.page_texts, start=1):
            for line in page_text.splitlines():
                out.append((idx, line.rstrip()))
    else:
        for line in doc.text.splitlines():
            out.append((1, line.rstrip()))
    return out


def _looks_like_heading(stripped: str) -> Optional[Tuple[str, str]]:
    if not stripped:
        return None
    if len(stripped) > 170:
        return None
    if stripped.endswith(".") and len(stripped.split()) > 12:
        return None

    m = NUMERIC_HEADING_RE.match(stripped)
    if m:
        num = m.group(1).strip()
        title = m.group(2).strip()
        return num, title

    m = ROMAN_HEADING_RE.match(stripped)
    if m:
        num = m.group(1).strip()
        title = m.group(2).strip()
        return num, title

    lowered = stripped.lower().strip(":")
    if lowered in ALLOWED_NAMED_HEADINGS:
        return lowered, stripped.strip(":").title()

    return None


def split_into_clauses(doc: Document) -> List[Clause]:
    rows = _iter_lines_with_pages(doc)
    clauses: List[Clause] = []

    current_num = "0"
    current_heading = "Preamble"
    buffer: List[str] = []
    start_page: Optional[int] = 1 if rows else None
    last_page: Optional[int] = 1 if rows else None

    def flush() -> None:
        nonlocal buffer, start_page, last_page, current_num, current_heading
        text = "\n".join(buffer).strip()
        if text:
            clauses.append(
                Clause(
                    clause_id=f"{doc.document_id}::clause::{current_num}",
                    document_id=doc.document_id,
                    heading=current_heading,
                    text=text,
                    page_start=start_page,
                    page_end=last_page,
                    metadata={"clause_number": current_num},
                )
            )
        buffer = []

    for page_no, line in rows:
        stripped = line.strip()
        if start_page is None:
            start_page = page_no
        last_page = page_no

        if not stripped:
            if buffer:
                buffer.append("")
            continue

        heading = _looks_like_heading(stripped)
        if heading:
            flush()
            current_num, current_heading = heading
            start_page = page_no
            last_page = page_no
            continue

        buffer.append(stripped)

    flush()
    return clauses


def ingest_path(path: Path) -> Document:
    raw = read_text(path)
    title = infer_title(raw.text, path)
    doc = Document(
        document_id=make_document_id(path, title),
        title=title,
        doc_type=infer_doc_type(raw.text, path),
        date=infer_date(raw.text),
        issuer=infer_issuer(raw.text),
        source_path=str(path),
        text=raw.text,
        page_texts=raw.page_texts,
        metadata={"circular_no": infer_circular_no(raw.text) or ""},
    )
    doc.clauses = split_into_clauses(doc)
    return doc


def ingest_many(paths: Iterable[Path]) -> List[Document]:
    return [ingest_path(path) for path in paths]


def collect_paths(root: Path) -> List[Path]:
    allowed = {".pdf", ".txt", ".md", ".json"}
    files: List[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in allowed:
            files.append(path)
    return sorted(set(files))