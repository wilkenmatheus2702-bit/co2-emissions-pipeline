"""Report step: run the SQL analyses, save CSVs and charts, write a run summary."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless rendering (CI, servers)
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .load import query  # noqa: E402

SQL_DIR = Path(__file__).parent / "sql"
REPORTS = ["top_emitters_latest", "per_capita_ranking", "focus_vs_baseline", "decoupling"]

# Chart styling (categorical order is fixed: Canada always blue, Brazil always orange).
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SERIES = {"CAN": "#2a78d6", "BRA": "#eb6834", "USA": "#1baf7a"}
CONTEXT = "#8a8984"
DECREASE, INCREASE = "#2a78d6", "#e34948"


def run_sql_reports(db_path: Path, reports_dir: Path, baseline_year: int) -> dict[str, pd.DataFrame]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for name in REPORTS:
        sql = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
        df = query(db_path, sql, {"baseline_year": baseline_year})
        df.to_csv(reports_dir / f"{name}.csv", index=False)
        results[name] = df
    return results


def _style(ax, title: str, subtitle: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.figure.text(0.02, 0.96, title, fontsize=13, fontweight="bold", color=INK, va="top")
    ax.figure.text(0.02, 0.905, subtitle, fontsize=9.5, color=INK_2, va="top")


def chart_per_capita_trend(db_path: Path, out: Path) -> Path:
    """Per-capita CO2 over time: Canada, Brazil, USA and the all-country average."""
    df = query(
        db_path,
        "SELECT iso_code, country, year, co2_per_capita_t FROM emissions "
        "WHERE iso_code IN ('CAN', 'BRA', 'USA') AND co2_per_capita_t IS NOT NULL",
    )
    avg = query(
        db_path,
        "SELECT year, SUM(co2_mt) * 1e6 / SUM(population) AS co2_per_capita_t FROM emissions "
        "WHERE co2_mt IS NOT NULL AND population > 0 GROUP BY year",
    )
    fig, ax = plt.subplots(figsize=(9, 5))
    fig.subplots_adjust(top=0.80, left=0.07, right=0.86, bottom=0.10)
    for iso, color in SERIES.items():
        s = df[df["iso_code"] == iso].sort_values("year")
        if s.empty:
            continue
        ax.plot(s["year"], s["co2_per_capita_t"], color=color, lw=2, label=s["country"].iloc[0])
        ax.annotate(
            f"{s['country'].iloc[0]}  {s['co2_per_capita_t'].iloc[-1]:.1f} t",
            (s["year"].iloc[-1], s["co2_per_capita_t"].iloc[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=INK,
        )
    ax.plot(avg["year"], avg["co2_per_capita_t"], color=CONTEXT, lw=2, ls="--", label="All countries")
    ax.annotate(
        f"All countries  {avg['co2_per_capita_t'].iloc[-1]:.1f} t",
        (avg["year"].iloc[-1], avg["co2_per_capita_t"].iloc[-1]),
        xytext=(6, 0),
        textcoords="offset points",
        va="center",
        fontsize=9,
        color=INK_2,
    )
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.legend(
        frameon=False, fontsize=9, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.08), labelcolor=INK_2
    )
    _style(ax, "CO₂ emissions per person", "Tonnes per person per year, fossil fuels and industry")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def chart_change_vs_baseline(focus: pd.DataFrame, baseline_year: int, out: Path) -> Path:
    """Horizontal bars: change in total CO2 since the baseline year, per focus country."""
    d = focus.dropna(subset=["co2_change_pct"]).sort_values("co2_change_pct", ascending=False)
    fig, ax = plt.subplots(figsize=(9, 0.45 * len(d) + 1.8))
    fig.subplots_adjust(top=0.82, left=0.17, right=0.95, bottom=0.08)
    colors = [DECREASE if v < 0 else INCREASE for v in d["co2_change_pct"]]
    ax.barh(d["country"], d["co2_change_pct"], color=colors, height=0.6)
    ax.axvline(0, color=INK_2, lw=1)
    span = d["co2_change_pct"].abs().max()
    for y, v in enumerate(d["co2_change_pct"]):
        label = f"{v:+.1f}%" if abs(v) < 1 else f"{v:+.0f}%"
        ax.text(
            v + (span * 0.015 if v >= 0 else -span * 0.015),
            y,
            label,
            va="center",
            ha="left" if v >= 0 else "right",
            fontsize=9,
            color=INK,
        )
    lo, hi = d["co2_change_pct"].min(), d["co2_change_pct"].max()
    ax.set_xlim(min(lo, 0) - span * 0.18, max(hi, 0) + span * 0.15)
    ax.xaxis.set_major_formatter(lambda x, _: "0%" if x == 0 else f"{x:+.0f}%")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    latest = int(focus["latest_year"].max())
    _style(
        ax,
        f"Change in total CO₂ emissions, {baseline_year}–{latest}",
        "Blue = emissions fell, red = emissions rose",
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)
    return out


def _md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |")
    return "\n".join(lines)


def write_summary(
    path: Path, run_meta: dict, audit: dict, quality_md: str, results: dict[str, pd.DataFrame]
) -> Path:
    dec = results["decoupling"]
    counts = dec["decoupling"].value_counts().to_dict() if not dec.empty else {}
    parts = [
        "# Pipeline run summary",
        "",
        f"- Run ID: `{run_meta['run_id']}` at {run_meta['run_at_utc']} UTC",
        f"- Source SHA-256: `{run_meta['source_sha256'][:16]}...` | config hash: `{run_meta['config_hash']}`",
        f"- Years: {run_meta['min_year']}–{run_meta['max_year']} | countries: {run_meta['countries']}",
        "",
        "## Row audit",
        "",
        _md_table(pd.DataFrame([audit])),
        "",
        "## Data quality",
        "",
        quality_md,
        "",
        "## Top 10 emitters (latest year)",
        "",
        _md_table(results["top_emitters_latest"]),
        "",
        "## Focus countries vs. baseline",
        "",
        _md_table(results["focus_vs_baseline"]),
        "",
        "## Decoupling (GDP vs. CO2)",
        "",
        f"Absolute: {counts.get('absolute', 0)} | relative: {counts.get('relative', 0)} | "
        f"none: {counts.get('none', 0)} (of {len(dec)} countries with 1M+ people)",
        "",
    ]
    path.write_text("\n".join(parts), encoding="utf-8")
    return path
