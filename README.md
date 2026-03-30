# SEBI Compliance Graph Agent

A faithful starter prototype for the Hyde challenge. It turns circular-like documents into:
- clause-level records
- extracted references
- structured obligations
- a simple compliance knowledge graph
- traceable answers with citations and gaps

## Project structure

```text
sebi_compliance_agent/
├── examples/
├── src/sebi_compliance_agent/
│   ├── api.py
│   ├── cli.py
│   ├── extraction.py
│   ├── graph_store.py
│   ├── ingestion.py
│   ├── models.py
│   ├── pipeline.py
│   └── query_engine.py
├── tests/
└── README.md
```

## Quick start

```bash
cd sebi_compliance_agent
export PYTHONPATH=src
python -m sebi_compliance_agent.cli --docs examples --stats --show-unresolved
python -m sebi_compliance_agent.cli --docs examples --question "What are the quarterly disclosure obligations for a listed entity?"
```

## Run tests

```bash
cd sebi_compliance_agent
export PYTHONPATH=src
python -m unittest discover -s tests -v
```

## Optional API

If FastAPI is installed:

```bash
cd sebi_compliance_agent
export PYTHONPATH=src
uvicorn sebi_compliance_agent.api:app --reload
```

Then:
- `POST /index` with `{ "path": "examples" }`
- `GET /ask?question=...`

## Next upgrades
- add layout-aware PDF extraction
- add true entity resolution for regulations/circular IDs
- add version and supersession logic
- add bank internal policy/control ingestion
- add evaluation datasets and human review screens
