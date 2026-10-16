"""Transform step: pure functions that turn the raw table into an analysis-ready one.

Every function takes a DataFrame and returns a new one (no in-place mutation),
which keeps each step independently testable.
"""

from __future__ import annotations

import pandas as pd

# Raw column -> clean column (units made explicit in the name).
COLUMN_MAP = {
    "country": "country",
    "iso_code": "iso_code",
    "year": "year",
    "population": "population",
    "gdp": "gdp_usd",
    "co2": "co2_mt",
    "co2_per_capita": "source_co2_per_capita_t",
    "coal_co2": "coal_co2_mt",
    "oil_co2": "oil_co2_mt",
    "gas_co2": "gas_co2_mt",
    "cement_co2": "cement_co2_mt",
    "flaring_co2": "flaring_co2_mt",
    "other_industry_co2": "other_industry_co2_mt",
}
KEY = ["iso_code", "year"]
FUELS = ["coal", "oil", "gas"]
COMPONENT_COLUMNS = [
    "coal_co2_mt",
    "oil_co2_mt",
    "gas_co2_mt",
    "cement_co2_mt",
    "flaring_co2_mt",
    "other_industry_co2_mt",
]


def select_and_rename(raw: pd.DataFrame) -> pd.DataFrame:
    """Keep only the columns we use, give them explicit, unit-bearing names and
    store every measure as float (so no step ever does integer division)."""
    df = raw[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)
    measures = [c for c in df.columns if c not in ("country", "iso_code", "year")]
    return df.astype({c: "float64" for c in measures} | {"year": "int64"})


def keep_countries(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop regional/income aggregates (e.g. "World", "Europe").

    In the source, real countries carry an ISO alpha-3 code; aggregates have
    none or an ``OWID_`` prefix. Returns the filtered frame and rows dropped.
    """
    iso = df["iso_code"].astype("string").str.strip()
    mask = iso.str.fullmatch(r"[A-Z]{3}").fillna(False).astype(bool)
    out = df.loc[mask].assign(iso_code=iso[mask])
    return out, int((~mask).sum())


def filter_years(df: pd.DataFrame, start: int, end: int | None) -> pd.DataFrame:
    mask = df["year"] >= start
    if end is not None:
        mask &= df["year"] <= end
    return df.loc[mask].copy()


def deduplicate(df: pd.DataFrame, key: list[str] = KEY) -> tuple[pd.DataFrame, int]:
    """Keep the last occurrence of each composite key. Returns rows removed."""
    out = df.drop_duplicates(subset=key, keep="last")
    return out, len(df) - len(out)


def _safe_ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    return (num / den).where(den > 0)


def add_metrics(df: pd.DataFrame, baseline_year: int) -> pd.DataFrame:
    """Add derived indicators.

    - ``co2_per_capita_t``: tonnes of CO2 per person (recomputed, not copied)
    - ``co2_per_gdp_kg``: kg of CO2 per US$ of GDP (carbon intensity)
    - ``yoy_change_pct``: change vs. the previous year, only when that year exists
    - ``change_vs_baseline_pct``: change vs. ``baseline_year``
    - ``<fuel>_share_pct``: share of total CO2 from coal, oil and gas
    """
    out = df.sort_values(KEY).reset_index(drop=True)

    out["co2_per_capita_t"] = _safe_ratio(out["co2_mt"] * 1e6, out["population"])
    out["co2_per_gdp_kg"] = _safe_ratio(out["co2_mt"] * 1e9, out["gdp_usd"])

    grouped = out.groupby("iso_code", sort=False)
    prev_co2 = grouped["co2_mt"].shift(1)
    prev_year = grouped["year"].shift(1)
    consecutive = prev_year == out["year"] - 1
    out["yoy_change_pct"] = ((_safe_ratio(out["co2_mt"], prev_co2) - 1) * 100).where(consecutive)

    baseline = out.loc[out["year"] == baseline_year].set_index("iso_code")["co2_mt"]
    base_values = out["iso_code"].map(baseline)
    out["change_vs_baseline_pct"] = (_safe_ratio(out["co2_mt"], base_values) - 1) * 100

    for fuel in FUELS:
        out[f"{fuel}_share_pct"] = _safe_ratio(out[f"{fuel}_co2_mt"], out["co2_mt"]) * 100

    return out


def transform(raw: pd.DataFrame, start_year: int, end_year: int | None, baseline_year: int):
    """Run every transform step. Returns the clean frame and a row-count audit trail."""
    audit = {"raw_rows": len(raw)}
    df = select_and_rename(raw)
    df, audit["aggregate_rows_dropped"] = keep_countries(df)
    df = filter_years(df, start_year, end_year)
    audit["rows_in_year_range"] = len(df)
    df, audit["duplicate_rows_dropped"] = deduplicate(df)
    df = add_metrics(df, baseline_year)
    audit["clean_rows"] = len(df)
    audit["countries"] = int(df["iso_code"].nunique())
    return df, audit
