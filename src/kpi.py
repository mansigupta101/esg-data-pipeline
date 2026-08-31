"""
kpi.py

Step 3 of the pipeline: compute portfolio-level ESG KPIs from the
cleaned, QA-passed data. Output is what a dashboard or reporting layer
would consume directly.

KPIs:
  - total_co2_by_entity      : latest-year CO2 per entity
  - emissions_intensity_gdp  : CO2 per unit GDP (proxy for transition risk)
  - yoy_change_pct           : year-over-year % change in CO2
  - portfolio_ghg_total      : sum of total_ghg across the whole portfolio, by year
  - data_completeness_pct    : share of expected entity-years with usable data
"""

import pandas as pd
from pathlib import Path


def total_co2_by_entity(df: pd.DataFrame, year: int) -> pd.DataFrame:
    return (
        df[df["year"] == year][["country", "co2"]]
        .sort_values("co2", ascending=False)
        .reset_index(drop=True)
    )


def emissions_intensity_gdp(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["co2_per_gdp_million"] = (out["co2"] * 1_000_000) / out["gdp"]
    return out[["country", "year", "co2_per_gdp_million"]]


def yoy_change_pct(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values(["country", "year"]).copy()
    out["yoy_change_pct"] = out.groupby("country")["co2"].pct_change() * 100
    return out[["country", "year", "yoy_change_pct"]]


def portfolio_ghg_total(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby("year", as_index=False)["total_ghg"].sum().rename(
        columns={"total_ghg": "portfolio_total_ghg"}
    )


def data_completeness_by_entity(df: pd.DataFrame) -> pd.DataFrame:
    out = df.groupby("country").apply(
        lambda g: round(1 - g.isna().mean().mean(), 4)
    ).reset_index(name="completeness_score")
    return out


def run(processed_path: Path, output_dir: Path):
    df = pd.read_csv(processed_path)
    latest_year = int(df["year"].max())

    output_dir.mkdir(parents=True, exist_ok=True)
    total_co2_by_entity(df, latest_year).to_csv(output_dir / "kpi_total_co2_latest.csv", index=False)
    emissions_intensity_gdp(df).to_csv(output_dir / "kpi_intensity_gdp.csv", index=False)
    yoy_change_pct(df).to_csv(output_dir / "kpi_yoy_change.csv", index=False)
    portfolio_ghg_total(df).to_csv(output_dir / "kpi_portfolio_ghg_total.csv", index=False)
    data_completeness_by_entity(df).to_csv(output_dir / "kpi_completeness_by_entity.csv", index=False)

    print(f"KPIs written to {output_dir} (latest year: {latest_year})")


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    run(
        processed_path=base / "data/processed/portfolio_clean.csv",
        output_dir=base / "data/processed/kpis",
    )
