"""Shared fixtures. Tests never touch the network: the raw file is a small
synthetic CSV served through a ``file://`` URL."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

RAW_COLUMNS = [
    "country",
    "year",
    "iso_code",
    "population",
    "gdp",
    "co2",
    "co2_per_capita",
    "coal_co2",
    "oil_co2",
    "gas_co2",
    "cement_co2",
    "flaring_co2",
    "other_industry_co2",
]


def raw_row(country, iso, year, pop, co2, gdp=None, coal=None, oil=None, gas=None):
    """Build one raw row. Components default to a 20/40/30/10 split of total CO2."""
    coal = co2 * 0.2 if coal is None else coal
    oil = co2 * 0.4 if oil is None else oil
    gas = co2 * 0.3 if gas is None else gas
    return {
        "country": country,
        "year": year,
        "iso_code": iso,
        "population": pop,
        "gdp": gdp,
        "co2": co2,
        "co2_per_capita": co2 * 1e6 / pop if pop else None,
        "coal_co2": coal,
        "oil_co2": oil,
        "gas_co2": gas,
        "cement_co2": co2 * 0.05,
        "flaring_co2": co2 * 0.03,
        "other_industry_co2": co2 * 0.02,
    }


@pytest.fixture
def raw_df() -> pd.DataFrame:
    rows = []
    # Canada: emissions fall 10% from 2005 to 2007, GDP grows.
    for year, co2, gdp in [
        (2004, 560, 1.20e12),
        (2005, 600, 1.25e12),
        (2006, 570, 1.30e12),
        (2007, 540, 1.35e12),
    ]:
        rows.append(raw_row("Canada", "CAN", year, 40_000_000, co2, gdp))
    # Brazil: emissions grow 20%.
    for year, co2, gdp in [(2005, 350, 1.8e12), (2006, 385, 1.9e12), (2007, 420, 2.0e12)]:
        rows.append(raw_row("Brazil", "BRA", year, 200_000_000, co2, gdp))
    # Aggregates that must be dropped.
    rows.append(raw_row("World", None, 2007, 8_000_000_000, 37_000))
    rows.append(raw_row("Europe", "", 2007, 750_000_000, 5_000))
    rows.append(raw_row("High-income (OWID)", "OWID_HIC", 2007, 1_200_000_000, 12_000))
    # Exact duplicate of a Brazil row (simulates a bad upstream append).
    rows.append(raw_row("Brazil", "BRA", 2007, 200_000_000, 420, 2.0e12))
    return pd.DataFrame(rows, columns=RAW_COLUMNS)


@pytest.fixture
def raw_csv(tmp_path: Path, raw_df: pd.DataFrame) -> Path:
    src = tmp_path / "upstream" / "owid-co2-data.csv"
    src.parent.mkdir()
    raw_df.to_csv(src, index=False)
    return src


@pytest.fixture
def config_file(tmp_path: Path, raw_csv: Path) -> Path:
    cfg = tmp_path / "pipeline.yaml"
    cfg.write_text(
        f"""
source:
  url: {raw_csv.as_uri()}
  cache_dir: data/raw
  max_age_days: 7
filters:
  start_year: 2005
  end_year: null
baseline_year: 2005
focus_countries: [CAN, BRA]
quality:
  max_null_share:
    co2_mt: 0.10
    population: 0.10
  per_capita_tolerance: 0.02
output:
  database: output/emissions.db
  reports_dir: output/reports
""",
        encoding="utf-8",
    )
    return cfg
