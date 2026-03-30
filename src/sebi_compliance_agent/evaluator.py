from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

from .graph_store import ComplianceGraph


@dataclass
class GoldReference:
    doc_name: str
    raw_reference: str
    canonical_title: str
    page: int
    clause_number: str


@dataclass
class ExtractionMetrics:
    n_gold: int
    n_pred: int
    true_positive: int
    precision: float
    recall: float
    f1: float
    title_hit_rate: float
    page_hit_rate: float


class ComplianceEvaluator:
    def __init__(self, graph: ComplianceGraph) -> None:
        self.graph = graph

    @staticmethod
    def load_gold_references(path: Path) -> List[GoldReference]:
        out: List[GoldReference] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            out.append(
                GoldReference(
                    doc_name=raw["doc_name"],
                    raw_reference=raw["raw_reference"],
                    canonical_title=raw["canonical_title"],
                    page=int(raw["page"]),
                    clause_number=str(raw["clause_number"]),
                )
            )
        return out

    @staticmethod
    def _norm(s: str) -> str:
        s = s.lower().strip()
        s = s.replace("securities and exchange board of india", "sebi")
        s = " ".join(s.split())
        return s

    def _predicted_references(self) -> List[dict]:
        preds = []
        for doc in self.graph.documents.values():
            doc_name = Path(doc.source_path).name
            for clause in doc.clauses:
                clause_no = str(clause.metadata.get("clause_number", ""))
                for ref in clause.references:
                    preds.append(
                        {
                            "doc_name": doc_name,
                            "canonical_title": self._norm((ref.title_hint or ref.normalized_target or "").strip()),
                            "page": int(ref.source_page_start or 1),
                            "clause_number": clause_no,
                        }
                    )
        return preds

    def evaluate_reference_extraction(self, gold_refs: List[GoldReference]) -> ExtractionMetrics:
        preds = self._predicted_references()

        gold_keys = set(
            (
                g.doc_name,
                self._norm(g.canonical_title),
                str(g.clause_number),
            )
            for g in gold_refs
        )

        pred_keys = set(
            (
                p["doc_name"],
                p["canonical_title"],
                str(p["clause_number"]),
            )
            for p in preds
        )

        tp = len(gold_keys & pred_keys)
        n_gold = len(gold_keys)
        n_pred = len(pred_keys)

        precision = tp / n_pred if n_pred else 0.0
        recall = tp / n_gold if n_gold else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        title_hits = 0
        page_hits = 0
        for g in gold_refs:
            matches = [
                p for p in preds
                if p["doc_name"] == g.doc_name
                and p["clause_number"] == str(g.clause_number)
                and p["canonical_title"] == self._norm(g.canonical_title)
            ]
            if matches:
                title_hits += 1
                if any(int(p["page"]) == int(g.page) for p in matches):
                    page_hits += 1

        title_hit_rate = title_hits / len(gold_refs) if gold_refs else 0.0
        page_hit_rate = page_hits / len(gold_refs) if gold_refs else 0.0

        return ExtractionMetrics(
            n_gold=n_gold,
            n_pred=n_pred,
            true_positive=tp,
            precision=precision,
            recall=recall,
            f1=f1,
            title_hit_rate=title_hit_rate,
            page_hit_rate=page_hit_rate,
        )

    @staticmethod
    def save_metrics(path: Path, metrics: ExtractionMetrics) -> None:
        path.write_text(json.dumps(asdict(metrics), indent=2), encoding="utf-8")