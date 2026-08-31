# ESG Portfolio Emissions Pipeline

A small ETL pipeline that ingests emissions data, runs QA/QC, computes
ESG KPIs, and serves them through a dashboard. Built as a scoped demo
of the kind of ESG data value chain used in bank risk/reporting functions
(ingestion → validation → KPI computation → reporting).

## Data

[Our World in Data CO2 & GHG dataset](https://github.com/owid/co2-data)
(public, no auth required). Ten countries (Norway, Sweden, Denmark,
Germany, UK, US, China, India, Brazil, Netherlands) are used as a
stand-in **portfolio** of reporting entities — public corporate-level
emissions data isn't freely available, so country-level data plays
the same structural role a bank's counterparty exposure book would.

## Architecture

```
S3 (raw) --> Lambda (ingest + QA/QC + KPI) --> S3 (processed / errors / kpis)
                                                          |
                                                          v
                                                  Plotly-Dash dashboard
```

- `src/ingest.py` — loads raw data, filters to the tracked portfolio and year range
- `src/qc_checks.py` — schema, completeness, range, and year-over-year consistency checks; rejects go to a separate table with a reason code, not silently dropped
- `src/kpi.py` — computes portfolio KPIs from QA-passed data
- `src/lambda_function.py` — AWS Lambda handler; same logic as above, wired to S3 via `boto3`, triggered on new file upload
- `src/run_local.py` — runs the full pipeline against local files (used to validate logic without live AWS access)
- `dashboard/app.py` — Plotly-Dash dashboard over the KPI outputs
- `tests/test_qc_checks.py` — unit tests for the QA/QC rules

**Note on AWS:** `lambda_function.py` is written to run against real S3
via `boto3` but has not been executed against a live AWS account —
this was built in an environment without AWS network access. The
pipeline logic itself is validated locally (`run_local.py`, `pytest`)
using the same functions the Lambda handler calls; only the storage
layer (local disk vs. S3) differs. Deploy and smoke-test in your own
AWS account before relying on it in production.

## KPIs

| KPI | Description |
|---|---|
| Total CO2 by entity | Latest-year emissions, ranked — portfolio exposure snapshot |
| Emissions intensity (CO2 / GDP) | Proxy for transition risk per unit of economic output |
| YoY % change | Year-over-year emissions trend per entity |
| Portfolio total GHG | Aggregate GHG across the whole tracked portfolio, over time |
| Data completeness score | Share of non-null fields per entity — flags entities with weaker disclosure |

## QA/QC checks

- **Schema check** — required fields (`country`, `year`, `co2`, `total_ghg`) present
- **Range check** — no physically implausible values (e.g. negative emissions)
- **Consistency check** — year-over-year change beyond a 50% threshold is flagged for review rather than auto-accepted (likely a reporting break, not a real shift)
- **Completeness score** — computed and surfaced as a KPI in its own right

## Running locally

```bash
pip install -r requirements.txt
python src/run_local.py       # runs ingest -> qc -> kpi against local files
python dashboard/app.py       # serves dashboard at http://127.0.0.1:8050
pytest tests/                 # runs QA/QC unit tests
```

## Deploying the Lambda (outline)

```bash
aws s3 mb s3://<raw-bucket>
aws s3 mb s3://<output-bucket>
# package src/ (with dependencies) and deploy:
aws lambda create-function \
  --function-name esg-pipeline \
  --runtime python3.12 \
  --handler lambda_function.handler \
  --environment Variables="{OUTPUT_BUCKET=<output-bucket>}" \
  --zip-file fileb://deployment.zip \
  --role <execution-role-arn>
# attach an S3 trigger on <raw-bucket> for ObjectCreated events
```

## Future improvements

- Orchestrate with **Airflow** instead of a single Lambda, for retries/backfills and dependency management across steps
- Add **dbt** models for the transformation layer, for lineage and testable SQL
- Replace country-level proxy data with a real corporate emissions dataset (e.g. CDP disclosures) if licensing allows
- Add data drift monitoring (flag when completeness or YoY-flag rates shift over time, not just per-run)
