"""Load step: write the clean table to SQLite and record run metadata."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

RUNS_DDL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          TEXT PRIMARY KEY,
    run_at_utc      TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    source_sha256   TEXT NOT NULL,
    config_hash     TEXT NOT NULL,
    clean_rows      INTEGER NOT NULL,
    countries       INTEGER NOT NULL,
    min_year        INTEGER,
    max_year        INTEGER,
    quality_passed  INTEGER NOT NULL
)
"""


def load_sqlite(
    df: pd.DataFrame,
    db_path: Path,
    focus_countries: tuple[str, ...],
    run_meta: dict,
) -> None:
    """Replace the ``emissions`` table and append one row to ``pipeline_runs``.

    The unique index on (iso_code, year) makes the database itself enforce the
    composite key, so a bad upstream change cannot silently create duplicates.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as con, con:
        df.to_sql("emissions", con, if_exists="replace", index=False)
        con.execute("CREATE UNIQUE INDEX ux_emissions_key ON emissions (iso_code, year)")
        pd.DataFrame({"iso_code": list(focus_countries)}).to_sql(
            "focus_countries", con, if_exists="replace", index=False
        )
        con.execute(RUNS_DDL)
        cols = ", ".join(run_meta)
        marks = ", ".join(f":{k}" for k in run_meta)
        con.execute(f"INSERT INTO pipeline_runs ({cols}) VALUES ({marks})", run_meta)


def query(db_path: Path, sql: str, params: dict | None = None) -> pd.DataFrame:
    with closing(sqlite3.connect(db_path)) as con:
        return pd.read_sql_query(sql, con, params=params or {})
