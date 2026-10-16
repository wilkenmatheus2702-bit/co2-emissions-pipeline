import math

import pandas as pd
import pytest

from emissions_pipeline import transform as t


@pytest.fixture
def clean_input(raw_df):
    return t.select_and_rename(raw_df)


def test_select_and_rename_gives_unit_bearing_names(clean_input):
    assert list(clean_input.columns) == list(t.COLUMN_MAP.values())
    assert "co2_mt" in clean_input and "co2" not in clean_input


def test_keep_countries_drops_aggregates(clean_input):
    out, dropped = t.keep_countries(clean_input)
    assert set(out["iso_code"]) == {"CAN", "BRA"}
    assert dropped == 3  # World (missing), Europe (empty), OWID_HIC (prefix)


def test_keep_countries_strips_whitespace():
    df = pd.DataFrame({"iso_code": [" CAN ", "can", "CANADA"], "year": [2000, 2000, 2000]})
    out, dropped = t.keep_countries(df)
    assert out["iso_code"].tolist() == ["CAN"]
    assert dropped == 2


def test_filter_years_inclusive_bounds(clean_input):
    out = t.filter_years(clean_input, 2005, 2006)
    assert out["year"].between(2005, 2006).all()
    assert set(out["year"]) == {2005, 2006}


def test_filter_years_open_end(clean_input):
    out = t.filter_years(clean_input, 2006, None)
    assert out["year"].min() == 2006 and out["year"].max() == 2007


def test_deduplicate_on_composite_key(clean_input):
    countries, _ = t.keep_countries(clean_input)
    out, removed = t.deduplicate(countries)
    assert removed == 1
    assert not out.duplicated(subset=t.KEY).any()


def _metrics(clean_input, baseline=2005):
    df, _ = t.keep_countries(clean_input)
    df, _ = t.deduplicate(df)
    return t.add_metrics(df, baseline).set_index(["iso_code", "year"])


def test_per_capita_is_recomputed(clean_input):
    m = _metrics(clean_input)
    # 600 Mt / 40M people = 15 t per person
    assert m.loc[("CAN", 2005), "co2_per_capita_t"] == pytest.approx(15.0)


def test_carbon_intensity(clean_input):
    m = _metrics(clean_input)
    # 600 Mt / US$1.25 trillion = 0.48 kg per US$
    assert m.loc[("CAN", 2005), "co2_per_gdp_kg"] == pytest.approx(0.48)


def test_yoy_change_only_for_consecutive_years():
    df = pd.DataFrame(
        {
            "iso_code": ["AAA"] * 3,
            "year": [2000, 2001, 2005],
            "co2_mt": [100.0, 110.0, 121.0],
            "population": [1e6] * 3,
            "gdp_usd": [None] * 3,
            "coal_co2_mt": [0.0] * 3,
            "oil_co2_mt": [0.0] * 3,
            "gas_co2_mt": [0.0] * 3,
        }
    )
    m = t.add_metrics(df, 2000).set_index("year")
    assert math.isnan(m.loc[2000, "yoy_change_pct"])
    assert m.loc[2001, "yoy_change_pct"] == pytest.approx(10.0)
    assert math.isnan(m.loc[2005, "yoy_change_pct"])  # 2002-2004 missing: no fake YoY


def test_change_vs_baseline(clean_input):
    m = _metrics(clean_input)
    assert m.loc[("CAN", 2007), "change_vs_baseline_pct"] == pytest.approx(-10.0)
    assert m.loc[("BRA", 2007), "change_vs_baseline_pct"] == pytest.approx(20.0)
    assert m.loc[("CAN", 2005), "change_vs_baseline_pct"] == pytest.approx(0.0)


def test_change_vs_baseline_missing_baseline_is_nan(clean_input):
    m = _metrics(clean_input, baseline=1990)
    assert m["change_vs_baseline_pct"].isna().all()


def test_fuel_shares(clean_input):
    m = _metrics(clean_input)
    row = m.loc[("BRA", 2006)]
    assert row["coal_share_pct"] == pytest.approx(20.0)
    assert row["oil_share_pct"] == pytest.approx(40.0)
    assert row["gas_share_pct"] == pytest.approx(30.0)


def test_zero_denominators_give_nan_not_inf():
    df = pd.DataFrame(
        {
            "iso_code": ["AAA"],
            "year": [2000],
            "co2_mt": [0.0],
            "population": [0.0],
            "gdp_usd": [0.0],
            "coal_co2_mt": [0.0],
            "oil_co2_mt": [0.0],
            "gas_co2_mt": [0.0],
        }
    )
    m = t.add_metrics(df, 2000)
    for col in ["co2_per_capita_t", "co2_per_gdp_kg", "coal_share_pct"]:
        assert math.isnan(m.loc[0, col])


def test_transform_does_not_mutate_input(raw_df):
    before = raw_df.copy()
    t.transform(raw_df, 2005, None, 2005)
    pd.testing.assert_frame_equal(raw_df, before)


def test_transform_audit_trail(raw_df):
    _, audit = t.transform(raw_df, 2005, None, 2005)
    assert audit == {
        "raw_rows": 11,
        "aggregate_rows_dropped": 3,
        "rows_in_year_range": 7,  # CAN 2004 filtered out
        "duplicate_rows_dropped": 1,
        "clean_rows": 6,
        "countries": 2,
    }
