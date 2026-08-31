"""
run_local.py

Runs the full pipeline (ingest -> qc_checks -> kpi) against local files,
in one command. This is what validates the pipeline logic in this
environment, where there is no AWS network access. It exercises the
exact same functions that lambda_function.py calls against S3 - only
the storage layer differs (local disk here, S3 in Lambda).
"""

from pathlib import Path
import ingest
import qc_checks
import kpi

BASE = Path(__file__).resolve().parent.parent


def main():
    print("1/3 Ingesting...")
    df = ingest.run(
        raw_path=BASE / "data/raw/owid-co2-data.csv",
        landing_path=BASE / "data/raw/portfolio_landing.csv",
    )
    print(f"    {len(df)} rows, {df['country'].nunique()} entities")

    print("2/3 Running QA/QC...")
    summary = qc_checks.run(
        landing_path=BASE / "data/raw/portfolio_landing.csv",
        processed_path=BASE / "data/processed/portfolio_clean.csv",
        errors_path=BASE / "data/errors/portfolio_rejects.csv",
    )
    print(f"    {summary}")

    print("3/3 Computing KPIs...")
    kpi.run(
        processed_path=BASE / "data/processed/portfolio_clean.csv",
        output_dir=BASE / "data/processed/kpis",
    )
    print("Done.")


if __name__ == "__main__":
    main()
