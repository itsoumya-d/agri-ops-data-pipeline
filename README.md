# agri-ops-data-pipeline

[![ci](https://github.com/itsoumya-d/agri-ops-data-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/itsoumya-d/agri-ops-data-pipeline/actions/workflows/ci.yml)

A tested reference for the data workflow behind an agri-tech operations
platform:

- Field events: check-ins, check-outs, inductions, hazards and biosecurity
  declarations.
- Validation and deduplication by event ID.
- Compliance enrichment: missing induction, missing/expired biosecurity
  declaration, visitor risk, high-severity hazards.
- DuckDB warehouse models: site activity, contractor compliance and hazard
  trends.
- Data-quality checks: uniqueness, accepted values and relationships.
- FastAPI ingest/metrics surface and synthetic demo data.

This is a **reference implementation**, not a claim of production AWS or
agri-tech experience. The AWS-shaped adapters are local; no live S3, SQS,
EventBridge, Lambda or DynamoDB is used in CI.

## Run

```bash
uv venv --python 3.12
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn agriops.api:app --reload
python -m agriops.generate
```

## License

MIT
