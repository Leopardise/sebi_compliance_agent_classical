from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List


@dataclass
class TuneResult:
    extractor_mode: str
    precision: float
    recall: float
    f1: float
    title_hit_rate: float
    page_hit_rate: float


def run_eval(docs: Path, gold_jsonl: Path, mode: str, metrics_out: Path) -> TuneResult:
    env = os.environ.copy()
    env["SEBI_EXTRACTOR_MODE"] = mode

    cmd = [
        sys.executable,
        "-m",
        "sebi_compliance_agent.cli",
        "--docs",
        str(docs),
        "--gold-jsonl",
        str(gold_jsonl),
        "--save-metrics",
        str(metrics_out),
    ]
    subprocess.run(cmd, check=True, env=env)

    data = json.loads(metrics_out.read_text(encoding="utf-8"))
    return TuneResult(
        extractor_mode=mode,
        precision=data["precision"],
        recall=data["recall"],
        f1=data["f1"],
        title_hit_rate=data["title_hit_rate"],
        page_hit_rate=data["page_hit_rate"],
    )


def autotune(docs: Path, gold_jsonl: Path, out_json: Path) -> None:
    modes = ["strict", "balanced", "permissive"]
    results: List[TuneResult] = []

    for mode in modes:
        metrics_out = out_json.parent / f"metrics_{mode}.json"
        result = run_eval(docs, gold_jsonl, mode, metrics_out)
        results.append(result)

    best = max(results, key=lambda r: (r.f1, r.title_hit_rate, r.precision))
    out_json.write_text(
        json.dumps(
            {
                "best_mode": best.extractor_mode,
                "results": [asdict(r) for r in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )