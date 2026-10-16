"""Orchestration: extract -> validate schema -> transform -> quality checks -> load -> report."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import extract, report, transform, validate
from .config import Config
from .load import load_sqlite

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    run_id: str
    audit: dict
    quality: validate.QualityReport
    database: Path
    reports_dir: Path


def run(cfg: Config, offline: bool = False) -> RunResult:
    run_id = uuid.uuid4().hex[:12]
    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    log.info("Run %s started (config %s)", run_id, cfg.config_hash)

    # 1. Extract
    src = extract.fetch(cfg.source_url, cfg.cache_dir, cfg.max_age_days, offline=offline)
    raw = extract.read_raw(src.path)
    log.info("Extracted %d rows (sha256 %s...)", len(raw), src.sha256[:12])

    # 2. Validate the raw schema before touching the data
    validate.check_schema(raw)

    # 3. Transform
    clean, audit = transform.transform(raw, cfg.start_year, cfg.end_year, cfg.baseline_year)
    log.info("Transform audit: %s", audit)

    # 4. Data-quality gate (the report is saved even when the run fails)
    quality = validate.run_quality_checks(clean, cfg.max_null_share, cfg.per_capita_tolerance)
    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    (cfg.reports_dir / "quality_report.json").write_text(
        json.dumps({"run_id": run_id, **quality.to_dict()}, indent=2), encoding="utf-8"
    )
    for check in quality.checks:
        level = (
            logging.INFO
            if check.passed
            else (logging.ERROR if check.severity == "error" else logging.WARNING)
        )
        log.log(level, "[%s] %s: %s", "PASS" if check.passed else "FAIL", check.name, check.detail)
    if not quality.passed:
        raise validate.DataQualityError(quality)

    # 5. Load
    run_meta = {
        "run_id": run_id,
        "run_at_utc": run_at,
        "source_url": cfg.source_url,
        "source_sha256": src.sha256,
        "config_hash": cfg.config_hash,
        "clean_rows": audit["clean_rows"],
        "countries": audit["countries"],
        "min_year": int(clean["year"].min()),
        "max_year": int(clean["year"].max()),
        "quality_passed": int(quality.passed),
    }
    load_sqlite(clean, cfg.database, cfg.focus_countries, run_meta)
    log.info("Loaded %d rows into %s", len(clean), cfg.database)

    # 6. Reports
    results = report.run_sql_reports(cfg.database, cfg.reports_dir, cfg.baseline_year)
    report.chart_per_capita_trend(cfg.database, cfg.reports_dir / "per_capita_trend.png")
    if not results["focus_vs_baseline"].dropna(subset=["co2_change_pct"]).empty:
        report.chart_change_vs_baseline(
            results["focus_vs_baseline"], cfg.baseline_year, cfg.reports_dir / "change_vs_baseline.png"
        )
    report.write_summary(cfg.reports_dir / "summary.md", run_meta, audit, quality.to_markdown(), results)
    log.info("Reports written to %s", cfg.reports_dir)

    return RunResult(run_id, audit, quality, cfg.database, cfg.reports_dir)
