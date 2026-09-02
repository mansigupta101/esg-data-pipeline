"""
Step 3 of the pipeline: compute portfolio-level ESG KPIs from the cleaned, 
QA-passed data. Output can be used directly for dashboard or reporting.

Script to calculate follwoing KPIs:
  - total_co2_by_entity      : latest-year CO2 per entity
  - emissions_intensity_gdp  : CO2 per unit GDP (proxy for transition risk)
  - yoy_change_pct           : year-over-year % change in CO2
  - portfolio_ghg_total      : sum of total_ghg across the whole portfolio, by year
  - data_completeness_pct    : share of expected entity-years with usable data
"""

import pandas as pd
from pathlib import Path


def total_co2_by_entity(df, year):
    """
    Rank entities by total CO2 for a given year.
    """
    return (
        df[df["year"] == year][["country", "co2"]]
        .sort_values("co2", ascending=False)
        .reset_index(drop=True)
    )


def emissions_intensity_gdp(df):
    """
    Emissions intensity: how much CO2 is produced per unit of economic output.
    Lower = more efficient economy relative to its emissions.

    Formula: (CO2 tonnes * 1,000,000) / GDP
      - CO2 in the dataset is in million tonnes, so multiplied by 1,000,000
        to convert it to tonnes.
      - Returns co2_per_gdp_million = tonnes of CO2 per $1 million of GDP.
    """
    out = df.copy()
    out["co2_per_gdp_million"] = (out["co2"] * 1_000_000) / out["gdp"]
    return out[["country", "year", "co2_per_gdp_million"]]


def yoy_change_pct(df):
    """
    Year-over-year percentage change in CO2, per entity.

    Formula: ((this_year - last_year) / last_year) * 100
    """
    out = df.sort_values(["country", "year"]).copy()
    out["yoy_change_pct"] = out.groupby("country")["co2"].pct_change() * 100
    return out[["country", "year", "yoy_change_pct"]]


def portfolio_ghg_total(df):
    """
    Total greenhouse gas emissions across the whole portfolio, per year.

    Formula: sum of total_ghg across all entities per year.
    """
    return df.groupby("year", as_index=False)["total_ghg"].sum().rename(
        columns={"total_ghg": "portfolio_total_ghg"}
    )


def data_completeness_by_entity(df):
    """
    Share of non-null values per entity, across all columns.

    Formula: 1 - (average share of null cells for that entity)
    1.0 = fully complete, 0.0 = fully empty.
    """
    out = df.groupby("country").apply(
        lambda g: round(1 - g.isna().mean().mean(), 4),
        include_groups=False,
    ).reset_index(name="completeness_score")
    return out


def run(processed_path, output_dir):
    """
    Runs all KPI calculations on the cleaned dataset and writes each result to its own CSV file in output_dir.
    """
    processed_path = Path(processed_path)
    output_dir = Path(output_dir)
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
