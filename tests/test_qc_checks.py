"""
Unit tests for the QA/QC rules. Run with: pytest tests/

"""

import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import qc_checks


def make_df():
    return pd.DataFrame({
        "country": ["A", "A", "B", "B"],
        "year": [2020, 2021, 2020, 2021],
        "co2": [100, 105, 50, -5],       # B/2021 is an implausible negative value
        "total_ghg": [120, None, 60, 65],  # A/2021 missing required field
    })


def test_check_schema_flags_missing_required_field():
    df = make_df()
    result = qc_checks.check_schema(df)
    assert result.iloc[1] == False  # A, 2021 missing total_ghg
    assert result.iloc[0] == True


def test_check_range_flags_negative_values():
    df = make_df()
    result = qc_checks.check_range(df)
    assert result.iloc[3] == False  # B, 2021 negative co2
    assert result.iloc[0] == True


def test_check_yoy_consistency_flags_large_jump():
    df = pd.DataFrame({
        "country": ["A", "A"],
        "year": [2020, 2021],
        "co2": [100, 300],  # 200% jump, exceeds 50% threshold
        "total_ghg": [120, 130],
    })
    result = qc_checks.check_yoy_consistency(df)
    assert result.iloc[1] == False


def test_completeness_score_range():
    df = make_df()
    score = qc_checks.completeness_score(df)
    assert 0 <= score <= 1


def test_run_end_to_end(tmp_path):
    landing = tmp_path / "landing.csv"
    processed = tmp_path / "processed.csv"
    errors = tmp_path / "errors.csv"
    make_df().to_csv(landing, index=False)

    summary = qc_checks.run(landing, processed, errors)

    assert summary["total_records"] == 4
    assert summary["rejected"] >= 1
    assert processed.exists()
    assert errors.exists()
