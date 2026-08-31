"""
ingest.py

Step 1 of the pipeline: pulls raw source data and prepares it for the
QA/QC stage. In production this file would run inside AWS Lambda,
triggered by an S3 PUT event on the raw data bucket. Locally, it reads
from disk to simulate that trigger so the pipeline can be tested without
live AWS credentials.

Data source: Our World in Data CO2 & GHG dataset (github.com/owid/co2-data).
Used as a public stand-in for corporate/portfolio-level emissions data,
since real MRV disclosures are not freely available. Countries here
represent a hypothetical lending/investment portfolio, analogous to how
a bank's risk function would track emissions exposure across counterparties.
"""

import pandas as pd
from pathlib import Path

# Hypothetical "portfolio" of reporting entities (countries standing in
# for counterparties / investees in a bank's exposure book).
PORTFOLIO = [
    "Norway", "Sweden", "Denmark", "Germany", "United Kingdom",
    "United States", "China", "India", "Brazil", "Netherlands",
]

COLUMNS = [
    "country", "iso_code", "year", "population", "gdp",
    "co2", "co2_per_capita", "co2_growth_prct",
    "methane", "nitrous_oxide", "total_ghg", "ghg_per_capita",
    "cumulative_co2", "share_global_co2",
]

START_YEAR = 2000
END_YEAR = 2023  # 2024 excluded: GDP not yet published for most entities


def load_raw(raw_path: Path) -> pd.DataFrame:
    """Load the full raw dataset from disk."""
    return pd.read_csv(raw_path)


def filter_portfolio(df: pd.DataFrame) -> pd.DataFrame:
    """Restrict to the tracked portfolio, relevant columns, and year range."""
    df = df[df["country"].isin(PORTFOLIO)]
    df = df[(df["year"] >= START_YEAR) & (df["year"] <= END_YEAR)]
    df = df[COLUMNS].reset_index(drop=True)
    return df


def run(raw_path: Path, landing_path: Path) -> pd.DataFrame:
    """Full ingestion step: load, filter, write landing file."""
    df = load_raw(raw_path)
    df = filter_portfolio(df)
    landing_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(landing_path, index=False)
    return df


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    df = run(
        raw_path=base / "data/raw/owid-co2-data.csv",
        landing_path=base / "data/raw/portfolio_landing.csv",
    )
    print(f"Ingested {len(df)} rows across {df['country'].nunique()} entities.")
