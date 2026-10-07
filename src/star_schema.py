"""
Step 4 in the pipeline: reshape the QA-passed and rejected data into the
four Power BI star-schema tables (FactEmissions, FactDataQuality,
DimEntity, DimDate) instead of one wide file per KPI.

Stable key: entity_id = iso_code (ISO3), already present in the OWID
output and matching the keys api_ingest.py uses for the World Bank API.
Using iso_code instead of country name avoids join breaks from name
variants ("United States" vs "USA" vs "United States of America").

Reads the same two files qc_checks.py already writes (processed_path,
errors_path), so no QA logic is duplicated here -- this step only
reshapes what already exists.
"""

import pandas as pd
from pathlib import Path

# country -> (region, income_group). income_group is a simplified World
# Bank-style label for this fixed 10-country portfolio, set by hand since
# it's not in the OWID data. Update if the PORTFOLIO list in ingest.py
# changes.
ENTITY_ATTRS = {
    "Norway":         ("Europe",         "High income"),
    "Sweden":         ("Europe",         "High income"),
    "Denmark":        ("Europe",         "High income"),
    "Germany":        ("Europe",         "High income"),
    "United Kingdom": ("Europe",         "High income"),
    "United States":  ("North America",  "High income"),
    "China":          ("Asia",           "Upper middle income"),
    "India":          ("Asia",           "Lower middle income"),
    "Brazil":         ("South America",  "Upper middle income"),
    "Netherlands":    ("Europe",         "High income"),
}

REQUIRED_FIELDS = ["country", "year", "co2", "total_ghg"]  # must match qc_checks.py
VALUE_COLUMNS = [
    "population", "gdp", "co2", "co2_per_capita", "co2_growth_prct",
    "methane", "nitrous_oxide", "total_ghg", "ghg_per_capita",
    "cumulative_co2", "share_global_co2",
]


def _load_full(processed_path, errors_path):
    """
    Recombine the QA-passed and rejected rows into one entity-year table
    (same shape as the pre-QC landing file, plus a reject_reason column
    that's blank for passed rows) so FactDataQuality can be built at
    entity-year grain instead of the entity-only grain qc_checks.py
    currently aggregates to.
    """
    clean = pd.read_csv(processed_path)
    clean["reject_reason"] = ""
    rejected = pd.read_csv(errors_path)
    full = pd.concat([clean, rejected], ignore_index=True)
    return full.sort_values(["country", "year"]).reset_index(drop=True)


def build_dim_entity(full):
    """One row per entity: id, name, region, category, latest year seen."""
    latest_year = full.groupby("country")["year"].max()
    rows = []
    for country, (region, income_group) in ENTITY_ATTRS.items():
        if country not in latest_year.index:
            continue  # portfolio changed and this script wasn't updated
        iso = full.loc[full["country"] == country, "iso_code"].iloc[0]
        rows.append({
            "entity_id": iso,
            "entity_name": country,
            "region": region,
            "category": income_group,
            "latest_reporting_year": int(latest_year[country]),
        })
    return pd.DataFrame(rows)


def build_dim_date(full):
    """One row per year in the data, plus simple time attributes."""
    years = sorted(full["year"].unique())
    return pd.DataFrame({
        "year": years,
        "previous_year": [y - 1 for y in years],
        "decade": [(y // 10) * 10 for y in years],
        "reporting_period": [f"CY{y}" for y in years],
    })


def build_fact_emissions(full):
    """
    One row per entity/year, QA-passed rows only (reject_reason == "").
    Emissions intensity formula matches kpi.emissions_intensity_gdp().

    NOTE: renewable_energy and energy_consumption are in the recommended
    FactEmissions schema but NOT in this pipeline's ingested columns
    (see COLUMNS in ingest.py) -- written here as empty columns rather
    than silently dropped, so the gap is visible in the output and in
    Power BI rather than hidden. To fill them, add OWID's
    "energy_per_capita" and "renewables_share_energy" to ingest.py's
    COLUMNS list and re-run the pipeline from step 1.
    """
    passed = full[full["reject_reason"] == ""].copy()
    passed["emissions_intensity_co2_per_gdp_million"] = (
        passed["co2"] * 1_000_000 / passed["gdp"]
    )
    passed["entity_id"] = passed["iso_code"]
    passed["energy_consumption"] = pd.NA
    passed["renewable_energy"] = pd.NA
    passed["source"] = "OWID CO2 & GHG dataset"

    cols = [
        "entity_id", "year", "co2", "total_ghg",
        "energy_consumption", "renewable_energy",
        "gdp", "population", "emissions_intensity_co2_per_gdp_million",
        "co2_per_capita", "ghg_per_capita", "source",
    ]
    return passed[cols].reset_index(drop=True)


def build_fact_data_quality(full):
    """
    One row per entity/year/check outcome. completeness_pct is row-level
    (share of non-null VALUE_COLUMNS for that row) -- a different grain
    than qc_checks.completeness_score(), which averages over the whole
    table. validity is the same pass/fail this row got from qc_checks.py.

    reconciliation_status is a placeholder ("not_computed"): the only
    reconciliation in the pipeline today is db.py's SQL-vs-pandas
    cross-check on 2 of the 5 KPIs, which isn't at entity-year grain.
    Flag, don't fabricate, until that's wired in properly.
    """
    out = full.copy()
    out["entity_id"] = out["iso_code"]
    out["completeness_pct"] = (
        out[VALUE_COLUMNS].notna().sum(axis=1) / len(VALUE_COLUMNS)
    ).round(4)
    out["validity"] = out["reject_reason"] == ""
    out["failed_checks"] = out["reject_reason"]
    out["missing_fields"] = out[REQUIRED_FIELDS].apply(
        lambda r: ";".join([c for c in REQUIRED_FIELDS if pd.isna(r[c])]), axis=1
    )
    out["reconciliation_status"] = "not_computed"

    cols = [
        "entity_id", "year", "completeness_pct", "validity",
        "failed_checks", "missing_fields", "reconciliation_status",
    ]
    return out[cols].reset_index(drop=True)


def run(processed_path, errors_path, output_dir):
    processed_path = Path(processed_path)
    errors_path = Path(errors_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    full = _load_full(processed_path, errors_path)

    dim_entity = build_dim_entity(full)
    dim_date = build_dim_date(full)
    fact_emissions = build_fact_emissions(full)
    fact_data_quality = build_fact_data_quality(full)

    dim_entity.to_csv(output_dir / "DimEntity.csv", index=False)
    dim_date.to_csv(output_dir / "DimDate.csv", index=False)
    fact_emissions.to_csv(output_dir / "FactEmissions.csv", index=False)
    fact_data_quality.to_csv(output_dir / "FactDataQuality.csv", index=False)

    print(f"DimEntity:        {len(dim_entity)} rows")
    print(f"DimDate:          {len(dim_date)} rows")
    print(f"FactEmissions:    {len(fact_emissions)} rows")
    print(f"FactDataQuality:  {len(fact_data_quality)} rows")
    print(f"Written to {output_dir}")


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    run(
        processed_path=base / "data/processed/portfolio_clean.csv",
        errors_path=base / "data/errors/portfolio_rejects.csv",
        output_dir=base / "outputs",
    )
