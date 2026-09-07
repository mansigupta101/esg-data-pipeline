"""
api_ingest.py

Alternative to ingest.py: instead of downloading a static CSV from
GitHub, this pulls live data directly from the World Bank Indicators
REST API (https://api.worldbank.org) -- no API key required.

Indicators used (confirmed current as of the Dec 2024 World Bank WDI
update, sourced from EDGAR v8.0 / JRC-IEA):
  - EN.GHG.CO2.MT.CE.AR5  -> co2        (CO2, Mt CO2e, excl. LULUCF)
  - EN.GHG.ALL.MT.CE.AR5  -> total_ghg  (all GHGs, Mt CO2e, excl. LULUCF)
  - NY.GDP.MKTP.CD        -> gdp        (GDP, current US$)

NOTE: the older indicator OWID-style pipelines might expect,
EN.ATM.CO2E.KT, has been discontinued by the World Bank ("archived") --
confirmed by calling it directly and getting an explicit archival
error back, not just a missing-data response. The two EN.GHG.* codes
above are their replacements.

This has NOT been run against the live API in this environment (no
network access to api.worldbank.org from this sandbox) -- the URL
structure and response parsing follow the World Bank's own documented
API contract, and the KPI-matching pandas/SQL logic elsewhere in this
project was cross-checked separately. Run this file yourself first and
confirm the printed row counts look right before trusting it further.
"""

import requests
import pandas as pd
from pathlib import Path

BASE_URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"

# Same 10 entities as ingest.py's PORTFOLIO, mapped to ISO3 codes the
# World Bank API requires.
PORTFOLIO_ISO3 = {
    "Norway": "NOR",
    "Sweden": "SWE",
    "Denmark": "DNK",
    "Germany": "DEU",
    "United Kingdom": "GBR",
    "United States": "USA",
    "China": "CHN",
    "India": "IND",
    "Brazil": "BRA",
    "Netherlands": "NLD",
}
ISO3_TO_NAME = {v: k for k, v in PORTFOLIO_ISO3.items()}

INDICATORS = {
    "co2": "EN.GHG.CO2.MT.CE.AR5",
    "total_ghg": "EN.GHG.ALL.MT.CE.AR5",
    "gdp": "NY.GDP.MKTP.CD",
}

START_YEAR = 2000
END_YEAR = 2023


def fetch_indicator(indicator_code, column_name, start_year=START_YEAR, end_year=END_YEAR, timeout=30):
    """
    Call the World Bank API for one indicator across the whole tracked
    portfolio in a single request, and return a tidy DataFrame:
    country, year, <column_name>.
    """
    countries_param = ";".join(PORTFOLIO_ISO3.values())
    url = BASE_URL.format(countries=countries_param, indicator=indicator_code)
    params = {"date": f"{start_year}:{end_year}", "format": "json", "per_page": 2000}

    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()  # raises if the HTTP call itself failed (4xx/5xx)
    payload = response.json()

    # World Bank returns errors as a single-element list with a "message" key,
    # e.g. for an archived/deleted indicator -- catch this explicitly rather
    # than letting it fail obscurely a few lines later.
    if isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], dict) and "message" in payload[0]:
        raise RuntimeError(f"World Bank API error for {indicator_code}: {payload[0]['message']}")

    meta, records = payload[0], payload[1]
    if meta.get("pages", 1) > 1:
        raise RuntimeError(
            f"{indicator_code} returned {meta['pages']} pages -- increase per_page, "
            f"current results are incomplete."
        )
    if not records:
        raise RuntimeError(f"No data returned for {indicator_code} -- check indicator code and date range.")

    rows = []
    for r in records:
        if r["value"] is None:
            continue  # World Bank includes null placeholders for years with no data yet
        rows.append({
            "country": ISO3_TO_NAME.get(r["countryiso3code"], r["country"]["value"]),
            "year": int(r["date"]),
            column_name: r["value"],
        })
    return pd.DataFrame(rows)


def run(landing_path):
    """Fetch all three indicators and merge into one landing file, same
    shape as ingest.py's output (country, year, co2, total_ghg, gdp)."""
    landing_path = Path(landing_path)

    co2_df = fetch_indicator(INDICATORS["co2"], "co2")
    ghg_df = fetch_indicator(INDICATORS["total_ghg"], "total_ghg")
    gdp_df = fetch_indicator(INDICATORS["gdp"], "gdp")

    merged = co2_df.merge(ghg_df, on=["country", "year"], how="outer") \
                    .merge(gdp_df, on=["country", "year"], how="outer")
    merged = merged.sort_values(["country", "year"]).reset_index(drop=True)

    landing_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(landing_path, index=False)
    return merged


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    df = run(landing_path=base / "data/raw/portfolio_landing_api.csv")
    print(f"Fetched {len(df)} rows across {df['country'].nunique()} entities from the World Bank API.")
    print(df.head())
