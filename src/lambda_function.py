"""

AWS Lambda entry point. Deploy this behind an S3 event trigger on the
raw-data bucket: whenever a new file lands in s3://<raw-bucket>/incoming/,
this function runs ingestion -> QA/QC -> KPI calculation and writes
results to the processed and errors prefixes of the output bucket.

This file is written to run in AWS (uses boto3 against real S3). It has
NOT been executed against live AWS in this environment — there is no
AWS credentials/network path available here. Logic is validated locally
via run_local.py, which exercises the same ingest/qc_checks/kpi modules
against local files. Deploy and smoke-test in your own AWS account
before relying on it.

Environment variables expected:
  OUTPUT_BUCKET   - bucket to write processed/, errors/, kpis/ to
"""

import os
import boto3
import pandas as pd
from io import StringIO

import ingest
import qc_checks
import kpi

s3 = boto3.client("s3")

OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "")


def _read_csv_from_s3(bucket: str, key: str) -> pd.DataFrame:
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(obj["Body"])


def _write_csv_to_s3(df: pd.DataFrame, bucket: str, key: str) -> None:
    buf = StringIO()
    df.to_csv(buf, index=False)
    s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue())


def handler(event, context):
    """
    Triggered by an S3 PUT event. Expects event['Records'][0]['s3'] with
    the source bucket/key of the newly landed raw file.
    """
    record = event["Records"][0]["s3"]
    source_bucket = record["bucket"]["name"]
    source_key = record["object"]["key"]

    raw_df = _read_csv_from_s3(source_bucket, source_key)
    landing_df = ingest.filter_portfolio(raw_df)

    # QA/QC checks operate on a DataFrame directly here (same logic as
    # qc_checks.run, adapted to avoid intermediate local files in Lambda)
    schema_ok = qc_checks.check_schema(landing_df)
    range_ok = qc_checks.check_range(landing_df)
    yoy_ok = qc_checks.check_yoy_consistency(landing_df)
    passed = schema_ok & range_ok & yoy_ok

    clean_df = landing_df[passed].copy()
    rejected_df = landing_df[~passed].copy()
    completeness = qc_checks.completeness_score(landing_df)

    _write_csv_to_s3(clean_df, OUTPUT_BUCKET, "processed/portfolio_clean.csv")
    _write_csv_to_s3(rejected_df, OUTPUT_BUCKET, "errors/portfolio_rejects.csv")

    if len(clean_df) > 0:
        latest_year = int(clean_df["year"].max())
        _write_csv_to_s3(
            kpi.total_co2_by_entity(clean_df, latest_year),
            OUTPUT_BUCKET, "kpis/kpi_total_co2_latest.csv",
        )
        _write_csv_to_s3(
            kpi.emissions_intensity_gdp(clean_df),
            OUTPUT_BUCKET, "kpis/kpi_intensity_gdp.csv",
        )
        _write_csv_to_s3(
            kpi.yoy_change_pct(clean_df),
            OUTPUT_BUCKET, "kpis/kpi_yoy_change.csv",
        )
        _write_csv_to_s3(
            kpi.portfolio_ghg_total(clean_df),
            OUTPUT_BUCKET, "kpis/kpi_portfolio_ghg_total.csv",
        )

    return {
        "statusCode": 200,
        "records_in": len(landing_df),
        "records_passed": len(clean_df),
        "records_rejected": len(rejected_df),
        "completeness_score": completeness,
    }
