from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dataset_generator import generate_dataset
from .evaluator import ComplianceEvaluator
from .pipeline import CompliancePipeline
from .query_engine import QueryEngine
from .autotune import autotune


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SEBI compliance graph agent")

    parser.add_argument("--docs", type=Path, help="Directory containing docs to index")
    parser.add_argument("--question", type=str, help="Question to ask after indexing")
    parser.add_argument("--stats", action="store_true", help="Print graph stats")
    parser.add_argument("--show-unresolved", action="store_true", help="Print unresolved references")

    parser.add_argument("--use-dense-retrieval", action="store_true", help="Enable dense retrieval if installed")
    parser.add_argument("--dense-model", type=str, default="BAAI/bge-small-en-v1.5")

    parser.add_argument("--gold-jsonl", type=Path, help="Gold references JSONL for extraction evaluation")
    parser.add_argument("--save-metrics", type=Path, help="Save metrics JSON")

    parser.add_argument("--generate-synth", action="store_true", help="Generate synthetic dataset")
    parser.add_argument("--synth-out", type=Path, help="Output folder for synthetic dataset")
    parser.add_argument("--synth-n-docs", type=int, default=10)
    parser.add_argument("--synth-min-chars", type=int, default=5000)
    parser.add_argument("--synth-max-chars", type=int, default=12000)
    parser.add_argument("--synth-max-depth-refs", type=int, default=5)
    parser.add_argument("--synth-seed", type=int, default=42)
    
    parser.add_argument("--autotune", action="store_true", help="Automatically tune extractor mode")
    parser.add_argument("--save-best-config", type=Path, help="Save autotune results JSON")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.generate_synth:
        if args.synth_out is None:
            raise ValueError("--synth-out is required with --generate-synth")

        generate_dataset(
            out_dir=args.synth_out,
            n_docs=args.synth_n_docs,
            min_chars=args.synth_min_chars,
            max_chars=args.synth_max_chars,
            max_depth_refs=args.synth_max_depth_refs,
            seed=args.synth_seed,
        )

        print(json.dumps({
            "status": "ok",
            "generated_at": str(args.synth_out),
            "docs_dir": str(args.synth_out / "docs"),
            "gold_references": str(args.synth_out / "gold_references.jsonl"),
        }, indent=2))
        return

    if args.docs is None:
        parser.print_help()
        return

    if not args.docs.exists():
        print(json.dumps({
            "status": "error",
            "message": f"Docs directory does not exist: {args.docs}"
        }, indent=2))
        return

    pipeline = CompliancePipeline(
        use_dense_retrieval=args.use_dense_retrieval,
        dense_model_name=args.dense_model,
    )
    system = pipeline.index_directory(args.docs)
    graph = system.graph
    retriever = system.retriever

    stats = graph.stats()
    if stats["documents"] == 0 or stats["clauses"] == 0:
        print(json.dumps({
            "status": "error",
            "message": "No ingestible supported files were found, or no clauses could be extracted.",
            "docs_path": str(args.docs),
            "indexed_paths": system.indexed_paths,
            "stats": stats,
        }, indent=2))
        return

    if args.stats:
        print(json.dumps(stats, indent=2))

    if args.show_unresolved:
        print(json.dumps(graph.unresolved_references(), indent=2))

    if args.gold_jsonl:
        evaluator = ComplianceEvaluator(graph)
        gold_refs = evaluator.load_gold_references(args.gold_jsonl)
        metrics = evaluator.evaluate_reference_extraction(gold_refs)
        print(json.dumps(metrics.__dict__, indent=2))
        if args.save_metrics:
            evaluator.save_metrics(args.save_metrics, metrics)

    if args.question:
        engine = QueryEngine(graph, retriever=retriever)
        answer = engine.answer(args.question)
        print(json.dumps(answer.to_dict(), indent=2))

    if args.autotune:
        if args.gold_jsonl is None:
            raise ValueError("--gold-jsonl is required with --autotune")
        if args.save_best_config is None:
            raise ValueError("--save-best-config is required with --autotune")
        autotune(args.docs, args.gold_jsonl, args.save_best_config)
        print(args.save_best_config.read_text(encoding="utf-8"))
        return


if __name__ == "__main__":
    main()