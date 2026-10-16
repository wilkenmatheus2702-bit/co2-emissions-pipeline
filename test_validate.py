import pytest

from emissions_pipeline import transform as t
from emissions_pipeline import validate as v


@pytest.fixture
def clean(raw_df):
    df, _ = t.transform(raw_df, 2005, None, 2005)
    return df


def _check(report, name):
    return next(c for c in report.checks if c.name == name)


def run(df, **kw):
    return v.run_quality_checks(df, kw.get("nulls", {"co2_mt": 0.1}), kw.get("tol", 0.02))


def test_schema_ok(raw_df):
    v.check_schema(raw_df)  # does not raise


def test_schema_missing_column(raw_df):
    with pytest.raises(v.SchemaError, match="co2"):
        v.check_schema(raw_df.drop(columns=["co2"]))


def test_clean_data_passes_all_checks(clean):
    report = run(clean)
    assert report.passed
    assert all(c.passed for c in report.checks)


def test_duplicate_key_fails(clean):
    report = run(pd_concat(clean, clean.iloc[[0]]))
    assert not _check(report, "unique_key").passed
    assert not report.passed


def test_negative_values_fail(clean):
    bad = clean.copy()
    bad.loc[0, "co2_mt"] = -1
    report = run(bad)
    assert not _check(report, "non_negative_values").passed
    assert not report.passed


def test_null_share_over_limit_fails(clean):
    bad = clean.copy()
    bad.loc[:2, "co2_mt"] = None  # 3 of 6 rows = 50%
    report = run(bad, nulls={"co2_mt": 0.1})
    check = _check(report, "null_share[co2_mt]")
    assert not check.passed and "50.0%" in check.detail


def test_null_share_unknown_column_fails(clean):
    report = run(clean, nulls={"does_not_exist": 0.1})
    assert not _check(report, "null_share[does_not_exist]").passed


def test_reconciliation_mismatch_is_only_a_warning(clean):
    bad = clean.copy()
    bad["source_co2_per_capita_t"] = bad["co2_per_capita_t"] * 1.10
    report = run(bad)
    check = _check(report, "per_capita_reconciliation")
    assert not check.passed and check.severity == "warning"
    assert report.passed  # warnings never block the run


def test_reconciliation_ignores_rounding_dominated_rows(clean):
    tiny = clean.copy()
    tiny["co2_mt"] = 0.007
    tiny["source_co2_per_capita_t"] = tiny["co2_per_capita_t"] * 1.10
    assert _check(run(tiny), "per_capita_reconciliation").passed


def test_components_above_total_warns(clean):
    bad = clean.copy()
    bad.loc[0, "coal_co2_mt"] = bad.loc[0, "co2_mt"] * 2
    assert not _check(run(bad), "components_not_above_total").passed


def test_year_gap_warns(clean):
    gap = clean[~((clean["iso_code"] == "CAN") & (clean["year"] == 2006))]
    check = _check(run(gap), "year_continuity")
    assert not check.passed and "CAN" in check.detail


def test_report_serialisation(clean):
    report = run(clean)
    assert report.to_dict()["passed"] is True
    md = report.to_markdown()
    assert md.startswith("| Check |") and "unique_key" in md


def test_data_quality_error_lists_failed_checks(clean):
    report = run(pd_concat(clean, clean.iloc[[0]]))
    err = v.DataQualityError(report)
    assert "unique_key" in str(err)


def pd_concat(*frames):
    import pandas as pd

    return pd.concat(frames, ignore_index=True)
