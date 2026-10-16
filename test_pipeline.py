"""End-to-end tests: run the whole pipeline on the synthetic fixture."""

import json
import sqlite3
from contextlib import closing

import pandas as pd
import pytest

from emissions_pipeline import cli
from emissions_pipeline.config import load_config
from emissions_pipeline.pipeline import run
from emissions_pipeline.validate import DataQualityError


@pytest.fixture
def result(config_file, tmp_path):
    return run(load_config(config_file, base_dir=tmp_path))


def test_database_has_clean_rows(result):
    with closing(sqlite3.connect(result.database)) as con:
        df = pd.read_sql("SELECT * FROM emissions", con)
    assert len(df) == 6
    assert set(df["iso_code"]) == {"CAN", "BRA"}
    assert not df.duplicated(["iso_code", "year"]).any()


def test_database_enforces_composite_key(result):
    with closing(sqlite3.connect(result.database)) as con, pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO emissions (iso_code, year) VALUES ('CAN', 2005)")


def test_run_is_recorded_for_traceability(config_file, tmp_path):
    cfg = load_config(config_file, base_dir=tmp_path)
    first, second = run(cfg), run(cfg)
    with closing(sqlite3.connect(cfg.database)) as con:
        runs = pd.read_sql("SELECT * FROM pipeline_runs ORDER BY run_at_utc", con)
    assert set(runs["run_id"]) == {first.run_id, second.run_id}
    assert runs["source_sha256"].nunique() == 1  # same input -> same checksum
    assert runs["config_hash"].iloc[0] == cfg.config_hash


def test_reruns_are_idempotent(config_file, tmp_path):
    cfg = load_config(config_file, base_dir=tmp_path)
    run(cfg)
    first = pd.read_csv(cfg.reports_dir / "focus_vs_baseline.csv")
    run(cfg)
    pd.testing.assert_frame_equal(first, pd.read_csv(cfg.reports_dir / "focus_vs_baseline.csv"))


def test_reports_are_written(result):
    names = {p.name for p in result.reports_dir.iterdir()}
    assert {
        "top_emitters_latest.csv",
        "per_capita_ranking.csv",
        "focus_vs_baseline.csv",
        "decoupling.csv",
        "quality_report.json",
        "summary.md",
        "per_capita_trend.png",
        "change_vs_baseline.png",
    } <= names


def test_focus_report_values(result):
    df = pd.read_csv(result.reports_dir / "focus_vs_baseline.csv").set_index("iso_code")
    assert df.loc["CAN", "co2_change_pct"] == -10.0
    assert df.loc["BRA", "co2_change_pct"] == 20.0
    assert df.loc["CAN", "latest_year"] == 2007


def test_top_emitters_shares_sum_to_100(result):
    df = pd.read_csv(result.reports_dir / "top_emitters_latest.csv")
    assert df["rank"].tolist() == [1, 2]
    assert df["share_of_total_pct"].sum() == pytest.approx(100.0, abs=0.2)


def test_decoupling_classification(result):
    df = pd.read_csv(result.reports_dir / "decoupling.csv").set_index("iso_code")
    assert df.loc["CAN", "decoupling"] == "absolute"  # GDP +8%, CO2 -10%
    assert df.loc["BRA", "decoupling"] == "none"  # GDP +11%, CO2 +20%


def test_quality_failure_stops_before_load(config_file, tmp_path, raw_csv):
    df = pd.read_csv(raw_csv)
    df.loc[df["country"] == "Canada", "co2"] = -5  # impossible values
    df.to_csv(raw_csv, index=False)
    cfg = load_config(config_file, base_dir=tmp_path)
    with pytest.raises(DataQualityError):
        run(cfg)
    assert not cfg.database.exists()  # nothing loaded
    report = json.loads((cfg.reports_dir / "quality_report.json").read_text())
    assert report["passed"] is False


def test_cli_exit_codes(config_file, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["--config", str(config_file)]) == 0
    assert cli.main(["--config", str(tmp_path / "missing.yaml")]) == 2


def test_cli_exit_code_on_quality_failure(config_file, tmp_path, raw_csv, monkeypatch):
    monkeypatch.chdir(tmp_path)
    df = pd.read_csv(raw_csv)
    df["population"] = None
    df.to_csv(raw_csv, index=False)
    assert cli.main(["--config", str(config_file)]) == 3


def test_sql_uses_real_division_even_for_integer_columns(tmp_path):
    """Regression test: SQLite divides INTEGER by INTEGER as integer (420/350 = 1)."""
    from emissions_pipeline.load import load_sqlite, query
    from emissions_pipeline.report import SQL_DIR

    df = pd.DataFrame(
        {
            "country": ["Brazil", "Brazil"],
            "iso_code": ["BRA", "BRA"],
            "year": [2005, 2007],
            "population": [200_000_000, 200_000_000],
            "gdp_usd": [18, 20],
            "co2_mt": [350, 420],
        }
    )
    db = tmp_path / "int.db"
    meta = {
        "run_id": "x",
        "run_at_utc": "now",
        "source_url": "u",
        "source_sha256": "s",
        "config_hash": "c",
        "clean_rows": 2,
        "countries": 1,
        "min_year": 2005,
        "max_year": 2007,
        "quality_passed": 1,
    }
    load_sqlite(df, db, ("BRA",), meta)
    out = query(db, (SQL_DIR / "decoupling.sql").read_text(), {"baseline_year": 2005})
    assert out.loc[0, "co2_change_pct"] == 20.0
    assert out.loc[0, "gdp_change_pct"] == pytest.approx(11.1)
