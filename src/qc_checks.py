"""
qc_checks.py

Step 2 of the pipeline: data quality assurance and control.

Every record is checked against a set of rules. Records that fail any
rule are written to the errors table with a reason code, rather than
silently dropped or silently passed through — this mirrors how a risk
data function needs traceability on *why* a record was rejected, not
just that it was.

Checks implemented:
  - Schema check      : required columns present and correctly typed
  - Completeness check: null values in required fields
  - Range check        : implausible values (e.g. negative emissions)
  - Consistency check  : year-over-year jump beyond a sane threshold
"""

import pandas as pd
from pathlib import Path

REQUIRED_FIELDS = ["country", "year", "co2", "total_ghg"]
YOY_JUMP_THRESHOLD = 0.5  # flag if a single-year change exceeds 50%


def check_schema(df: pd.DataFrame) -> pd.Series:
    """True where a row has all required fields present (non-null)."""
    return df[REQUIRED_FIELDS].notna().all(axis=1)


def check_range(df: pd.DataFrame) -> pd.Series:
    """True where emissions values are physically plausible (non-negative)."""
    return (df["co2"].fillna(0) >= 0) & (df["total_ghg"].fillna(0) >= 0)


def check_yoy_consistency(df: pd.DataFrame) -> pd.Series:
    """
    True where a country's year-over-year change in co2 is within a
    plausible range. Large jumps often indicate a reporting break or
    methodology change rather than a real-world event, and are worth
    a human review rather than automatic inclusion.
    """
    df = df.sort_values(["country", "year"])
    pct_change = df.groupby("country")["co2"].pct_change().abs()
    flags = pct_change.isna() | (pct_change <= YOY_JUMP_THRESHOLD)
    return flags.reindex(df.index)


def completeness_score(df: pd.DataFrame) -> float:
    """Share of non-null cells across the full table, 0-1."""
    return round(1 - df.isna().mean().mean(), 4)


def run(landing_path: Path, processed_path: Path, errors_path: Path) -> dict:
    df = pd.read_csv(landing_path)

    schema_ok = check_schema(df)
    range_ok = check_range(df)
    yoy_ok = check_yoy_consistency(df)

    passed = schema_ok & range_ok & yoy_ok
    clean = df[passed].copy()
    rejected = df[~passed].copy()

    # Attach a reason code so rejects are actionable, not just discarded
    reasons = []
    for idx in rejected.index:
        r = []
        if not schema_ok[idx]:
            r.append("missing_required_field")
        if not range_ok[idx]:
            r.append("implausible_negative_value")
        if not yoy_ok[idx]:
            r.append("yoy_jump_exceeds_threshold")
        reasons.append(";".join(r))
    rejected["reject_reason"] = reasons

    processed_path.parent.mkdir(parents=True, exist_ok=True)
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(processed_path, index=False)
    rejected.to_csv(errors_path, index=False)

    summary = {
        "total_records": len(df),
        "passed": len(clean),
        "rejected": len(rejected),
        "completeness_score": completeness_score(df),
    }
    return summary


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    summary = run(
        landing_path=base / "data/raw/portfolio_landing.csv",
        processed_path=base / "data/processed/portfolio_clean.csv",
        errors_path=base / "data/errors/portfolio_rejects.csv",
    )
    print(summary)
