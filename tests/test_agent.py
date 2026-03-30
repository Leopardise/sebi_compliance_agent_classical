from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from sebi_compliance_agent.dataset_generator import generate_dataset
from sebi_compliance_agent.evaluator import ComplianceEvaluator
from sebi_compliance_agent.pipeline import CompliancePipeline
from sebi_compliance_agent.query_engine import QueryEngine


class ComplianceAgentTests(unittest.TestCase):
    def make_docs(self, root: Path) -> None:
        (root / 'circular.txt').write_text(textwrap.dedent('''
            SEBI Circular on Quarterly Disclosure Obligations
            Date: March 15, 2026
            Circular No.: SEBI/HO/CFD/POD-1/P/CIR/2026/15
            Issued by Securities and Exchange Board of India

            1. Scope
            This circular applies to every listed entity and bank acting as an intermediary.

            2. Quarterly disclosures
            Every listed entity shall disclose material compliance deviations on a quarterly basis to the stock exchange within 30 days of the end of the quarter.
            This circular should be read with Regulation 30 and Clause 4 of the Master Circular on Listing Obligations.

            3. Record keeping
            The bank must maintain a compliance register and policy log for inspection and furnish the same promptly upon request.
        '''), encoding='utf-8')

        (root / 'master_circular.txt').write_text(textwrap.dedent('''
            Master Circular on Listing Obligations
            Date: January 22, 2026
            Circular No.: SEBI/HO/CFD/MASTER/2026/22
            Issued by Securities and Exchange Board of India

            1. Definitions
            This master circular consolidates prior circular guidance for listed entities.

            4. Disclosure control
            A listed entity shall maintain internal controls for disclosure review, board approval, and disclosure filing.
        '''), encoding='utf-8')

        (root / 'regulation_30.txt').write_text(textwrap.dedent('''
            SEBI Listing Regulations - Regulation 30
            Date: January 22, 2026
            Issued by Securities and Exchange Board of India

            30. Material events disclosure
            A listed entity shall disclose material events and maintain adequate documentation for review.
        '''), encoding='utf-8')

    def test_index_and_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_docs(root)
            system = CompliancePipeline().index_directory(root)
            graph = system.graph
            self.assertEqual(graph.stats()['documents'], 3)
            self.assertGreaterEqual(graph.stats()['obligations'], 3)

            engine = QueryEngine(graph, retriever=system.retriever)
            answer = engine.answer('What are the quarterly disclosure obligations for a listed entity?')
            self.assertTrue(answer.cited_clause_ids)
            self.assertTrue(any('listed entity' in r.lower() for r in answer.rationale))

    def test_unresolved_references_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_docs(root)
            (root / 'orphan.txt').write_text(textwrap.dedent('''
                Orphan Circular
                Date: March 20, 2026

                1. Dependency
                This circular should be read with Regulation 999 and Clause 98 of the Legacy Act, 1950.
            '''), encoding='utf-8')
            graph = CompliancePipeline().index_directory(root).graph
            unresolved = graph.unresolved_references()
            self.assertTrue(unresolved)

    def test_synthetic_generation_and_eval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "synth"
            generate_dataset(out_dir=out, n_docs=3, min_chars=5000, max_chars=7000, max_depth_refs=3, seed=7)
            docs = out / "docs"
            eval_jsonl = out / "eval_cases.jsonl"

            system = CompliancePipeline().index_directory(docs)
            evaluator = ComplianceEvaluator(system.graph, system.retriever)
            cases = evaluator.load_cases(eval_jsonl)
            metrics = evaluator.run(cases, top_k=5)

            self.assertEqual(metrics.n_cases, len(cases))
            self.assertGreaterEqual(metrics.reference_coverage, 0.0)


if __name__ == '__main__':
    unittest.main()