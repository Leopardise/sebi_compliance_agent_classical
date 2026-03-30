from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI
except Exception:  # pragma: no cover
    FastAPI = None  # type: ignore

from .pipeline import CompliancePipeline
from .query_engine import QueryEngine

app = FastAPI(title='SEBI Compliance Graph Agent') if FastAPI else None
_pipeline: Optional[CompliancePipeline] = None
_engine: Optional[QueryEngine] = None


if app:
    @app.post('/index')
    def index_docs(path: str):
        global _pipeline, _engine
        _pipeline = CompliancePipeline()
        graph = _pipeline.index_directory(Path(path))
        _engine = QueryEngine(graph)
        return graph.stats()


    @app.get('/ask')
    def ask(question: str):
        if _engine is None:
            return {'error': 'Index documents first using POST /index'}
        return _engine.answer(question).to_dict()
