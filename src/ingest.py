"""
Step 1 in the pipeline: Download raw source data and prepare it for the QA/QC stage.

Script to load emissions data from OWID CO2 & GHG dataset (github.com/owid/co2-data), 
filter it down to 10 countries (which is used as a stand-in 
portfolio-of-reporting-entities in this project), and 
prepare the filtered dataset for QA/QC step.
"""

import pandas as pd
from pathlib import Path
import urllib.request


"""
------------ Download raw data from source ------------------
"""
RAW_DATA_URL = "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv"

def download_raw(raw_path):
    """
    Download the raw OWID dataset if it isn't already on disk.
    Skips the download if the file already exists, so re-runs don't
    re-fetch a 14MB file every time.
    """
    raw_path = Path(raw_path)
    if raw_path.exists():
        return raw_path
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(RAW_DATA_URL, raw_path)
    return raw_path

    
"""
Hypothetical portfolio of reporting entities (countries standing in for counterparties/investees in a bank's exposure book).

------------ Preparing data for QC/QC --------------------
"""

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
END_YEAR = 2023 


def load_raw(raw_path):
    """Load the full raw dataset from disk."""
    return pd.read_csv(raw_path)


def filter_portfolio(df):
    """Subset to the defined portfolio, relevant columns, and year range."""
    df = df[df["country"].isin(PORTFOLIO)]
    df = df[(df["year"] >= START_YEAR) & (df["year"] <= END_YEAR)]
    df = df[COLUMNS].reset_index(drop=True)
    return df


def run(raw_path, landing_path):
    """Complete ingestion pipeline: download (if needed), load, filter, write landing file."""
    raw_path = Path(raw_path)
    landing_path = Path(landing_path)
    download_raw(raw_path)
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
