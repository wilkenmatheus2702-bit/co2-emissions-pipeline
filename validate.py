"""Validation: a schema check on the raw input and data-quality checks on the clean table.

Checks with severity ``error`` stop the pipeline; ``warning`` checks are
reported but do not block the run.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd

from .transform import COLUMN_MAP, COMPONENT_COLUMNS, KEY

MIN_CO2_FOR_RECONCILIATION_MT = 0.1


class SchemaError(ValueError):
    """Raised when the raw input is missing required columns."""


class DataQualityError(RuntimeError):
    """Raised when at least one error-level quality check fails."""

    def __init__(self, report: QualityReport):
        failed = ", ".join(c.name for c in report.failed_errors)
        super().__init__(f"Data quality checks failed: {failed}")
        self.report = report


@dataclass
class CheckResult:
    name: str
    passed: bool
    severity: str  # "error" | "warning"
    detail: str


@dataclass
class QualityReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def failed_errors(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    @property
    def passed(self) -> bool:
        return not self.failed_errors

    def to_dict(self) -> dict:
        return {"passed": self.passed, "checks": [asdict(c) for c in self.checks]}

    def to_markdown(self) -> str:
        lines = ["| Check | Severity | Result | Detail |", "|---|---|---|---|"]
        for c in self.checks:
            status = "PASS" if c.passed else "FAIL"
            lines.append(f"| {c.name} | {c.severity} | {status} | {c.detail} |")
        return "\n".join(lines)


def check_schema(raw: pd.DataFrame) -> None:
    missing = sorted(set(COLUMN_MAP) - set(raw.columns))
    if missing:
        raise SchemaError(f"Raw data is missing required columns: {missing}")


def _unique_key(df: pd.DataFrame) -> CheckResult:
    dupes = int(df.duplicated(subset=KEY).sum())
    return CheckResult("unique_key", dupes == 0, "error", f"{dupes} duplicate (iso_code, year) rows")


def _non_negative(df: pd.DataFrame) -> CheckResult:
    cols = ["population", "co2_mt", *COMPONENT_COLUMNS]
    bad = {c: int((df[c] < 0).sum()) for c in cols if (df[c] < 0).any()}
    return CheckResult("non_negative_values", not bad, "error", f"negative values: {bad or 'none'}")


def _null_share(df: pd.DataFrame, column: str, max_share: float) -> CheckResult:
    if column not in df.columns:
        return CheckResult(f"null_share[{column}]", False, "error", "column not found")
    share = float(df[column].isna().mean()) if len(df) else 0.0
    return CheckResult(
        f"null_share[{column}]",
        share <= max_share,
        "error",
        f"{share:.1%} missing (limit {max_share:.0%})",
    )


def _per_capita_reconciliation(df: pd.DataFrame, tolerance: float) -> CheckResult:
    both = df[["co2_mt", "co2_per_capita_t", "source_co2_per_capita_t"]].dropna()
    # The source rounds total CO2 to 0.001 Mt. For micro-states (e.g. 0.007 Mt)
    # that rounding alone moves per-capita values by ~5%, so they are excluded.
    both = both[both["co2_mt"] >= MIN_CO2_FOR_RECONCILIATION_MT]
    rel = (both["co2_per_capita_t"] / both["source_co2_per_capita_t"] - 1).abs()
    off = int((rel > tolerance).sum())
    return CheckResult(
        "per_capita_reconciliation",
        off == 0,
        "warning",
        f"{off} of {len(both)} rows differ from source by more than {tolerance:.0%}",
    )


def _components_sum(df: pd.DataFrame) -> CheckResult:
    total = df[COMPONENT_COLUMNS].sum(axis=1, min_count=1)
    rows = df["co2_mt"].notna() & total.notna()
    over = int((total[rows] > df.loc[rows, "co2_mt"] * 1.01 + 0.01).sum())
    return CheckResult(
        "components_not_above_total",
        over == 0,
        "warning",
        f"{over} rows where fuel/industry components exceed total CO2",
    )


def _year_continuity(df: pd.DataFrame) -> CheckResult:
    gaps = df.sort_values(KEY).groupby("iso_code")["year"].diff().gt(1)
    countries = sorted(df.loc[gaps.fillna(False).astype(bool), "iso_code"].unique())
    return CheckResult(
        "year_continuity",
        not countries,
        "warning",
        f"{len(countries)} countries with gaps in the yearly series"
        + (f": {', '.join(countries[:10])}" if countries else ""),
    )


def run_quality_checks(
    df: pd.DataFrame, max_null_share: dict[str, float], per_capita_tolerance: float
) -> QualityReport:
    report = QualityReport()
    report.checks.append(_unique_key(df))
    report.checks.append(_non_negative(df))
    for col, share in max_null_share.items():
        report.checks.append(_null_share(df, col, share))
    report.checks.append(_per_capita_reconciliation(df, per_capita_tolerance))
    report.checks.append(_components_sum(df))
    report.checks.append(_year_continuity(df))
    return report
