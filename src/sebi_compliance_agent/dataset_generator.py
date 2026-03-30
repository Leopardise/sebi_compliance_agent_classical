from __future__ import annotations

import json
import random
from pathlib import Path
from typing import List


SUBJECTS = [
    "bank", "custodian", "mutual fund", "listed entity",
    "investment adviser", "research analyst", "depository"
]

ACTIONS = [
    "maintain records", "submit a quarterly report", "disclose deviations",
    "furnish a certificate", "appoint a compliance officer",
    "maintain an internal policy register", "file an intimation"
]

REFERENCED_DOC_TITLES = [
    "Master Circular for Custodians",
    "Master Circular for Mutual Funds",
    "SEBI (Mutual Funds) Regulations, 2026",
    "SEBI (Investment Advisers) Regulations, 2013",
    "Securities and Exchange Board of India Act, 1992",
    "Cyber Resilience Framework Circular",
    "Disclosure and Investor Protection Guidelines"
]


def _rand_sentence(rng: random.Random, min_words: int, max_words: int) -> str:
    vocab = [
        "compliance", "entity", "framework", "obligation", "monitoring",
        "guidance", "inspection", "record", "reporting", "evidence",
        "internal", "audit", "oversight", "review", "applicable",
        "disclosure", "submission", "governance", "risk", "board",
        "control", "documentation", "certification", "implementation"
    ]
    n = rng.randint(min_words, max_words)
    return " ".join(rng.choice(vocab) for _ in range(n)).capitalize() + "."


def generate_dataset(
    out_dir: Path,
    n_docs: int = 10,
    min_chars: int = 5000,
    max_chars: int = 12000,
    max_depth_refs: int = 5,
    seed: int = 42,
) -> None:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    docs_dir = out_dir / "docs"
    docs_dir.mkdir(exist_ok=True)

    gold_refs_path = out_dir / "gold_references.jsonl"

    with gold_refs_path.open("w", encoding="utf-8") as gold_f:
        for i in range(n_docs):
            title = f"Synthetic Circular {i+1} on Compliance Operations"
            doc_name = f"synthetic_doc_{i+1}.txt"
            lines = [
                title,
                "Date: March 30, 2026",
                "Issued by Securities and Exchange Board of India",
                ""
            ]

            clause_idx = 1
            while sum(len(x) for x in lines) < rng.randint(min_chars, max_chars):
                lines.append(f"{clause_idx}. Operational Requirements {clause_idx}")

                for _ in range(rng.randint(4, 8)):
                    lines.append(_rand_sentence(rng, 12, 28))

                subject = rng.choice(SUBJECTS)
                action = rng.choice(ACTIONS)
                lines.append(
                    f"Every {subject} shall {action} within {rng.randint(2, 30)} days and maintain an audit trail for inspection."
                )

                n_refs = rng.randint(1, max_depth_refs)
                for _ in range(n_refs):
                    title_ref = rng.choice(REFERENCED_DOC_TITLES)
                    clause_ref = f"{rng.randint(1, 12)}.{rng.randint(1, 5)}"
                    raw = f"This circular shall be read with Clause {clause_ref} of the {title_ref}."
                    lines.append(raw)

                    gold_f.write(json.dumps({
                        "doc_name": doc_name,
                        "raw_reference": raw,
                        "canonical_title": title_ref,
                        "page": 1,
                        "clause_number": str(clause_idx),
                    }) + "\n")

                lines.append("")
                clause_idx += 1

            (docs_dir / doc_name).write_text("\n".join(lines), encoding="utf-8")