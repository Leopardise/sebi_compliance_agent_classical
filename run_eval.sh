#!/usr/bin/env bash
set -e

ROOT="synth_data"

python -m sebi_compliance_agent.cli \
  --generate-synth \
  --synth-out "$ROOT" \
  --synth-n-docs 10 \
  --synth-min-chars 5000 \
  --synth-max-chars 12000 \
  --synth-max-depth-refs 5 \
  --synth-seed 42

python -m sebi_compliance_agent.cli \
  --docs "$ROOT/docs" \
  --stats

python -m sebi_compliance_agent.cli \
  --docs "$ROOT/docs" \
  --gold-jsonl "$ROOT/gold_references.jsonl" \
  --save-metrics "$ROOT/metrics.json"

for i in 1 2 3 4 5
do
  echo "===== QUESTION $i ====="
  python -m sebi_compliance_agent.cli \
    --docs "$ROOT/docs" \
    --question "What references are made in Synthetic Circular $i on Compliance Operations?"
done

echo "===== METRICS ====="
cat "$ROOT/metrics.json"