from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .extraction import enrich_clause
from .graph_store import ComplianceGraph
from .ingestion import collect_paths, ingest_many
from .retrieval import HybridRetriever


@dataclass
class IndexedComplianceSystem:
    graph: ComplianceGraph
    retriever: HybridRetriever
    indexed_paths: list[str]


class CompliancePipeline:
    def __init__(self, use_dense_retrieval: bool = False, dense_model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.use_dense_retrieval = use_dense_retrieval
        self.dense_model_name = dense_model_name

    def index_paths(self, paths: Iterable[Path]) -> IndexedComplianceSystem:
        graph = ComplianceGraph()
        path_list = list(paths)
        documents = ingest_many(path_list)

        for document in documents:
            document.clauses = [enrich_clause(clause) for clause in document.clauses]
            graph.add_document(document)

        graph.resolve_pending_references()

        retriever = HybridRetriever(
            clauses=list(graph.clauses.values()),
            use_dense=self.use_dense_retrieval,
            dense_model_name=self.dense_model_name,
        )

        return IndexedComplianceSystem(
            graph=graph,
            retriever=retriever,
            indexed_paths=[str(p) for p in path_list],
        )

    def index_directory(self, root: Path) -> IndexedComplianceSystem:
        return self.index_paths(collect_paths(root))