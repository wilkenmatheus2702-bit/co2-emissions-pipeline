"""Load and validate the pipeline configuration."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ISO3 = re.compile(r"^[A-Z]{3}$")


class ConfigError(ValueError):
    """Raised when the configuration file is invalid."""


@dataclass(frozen=True)
class Config:
    source_url: str
    cache_dir: Path
    max_age_days: float
    start_year: int
    end_year: int | None
    baseline_year: int
    focus_countries: tuple[str, ...]
    max_null_share: dict[str, float] = field(default_factory=dict)
    per_capita_tolerance: float = 0.02
    database: Path = Path("output/emissions.db")
    reports_dir: Path = Path("output/reports")
    config_hash: str = ""


def load_config(path: str | Path, base_dir: str | Path | None = None) -> Config:
    """Read a YAML config file and return a validated :class:`Config`.

    Relative paths inside the file are resolved against ``base_dir``
    (default: the current working directory).
    """
    path = Path(path)
    try:
        raw_text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Cannot read config {path}: {exc}") from exc
    base = Path(base_dir) if base_dir else Path.cwd()

    try:
        source = data["source"]
        filters = data.get("filters", {})
        quality = data.get("quality", {})
        output = data.get("output", {})
        cfg = Config(
            source_url=str(source["url"]),
            cache_dir=base / source.get("cache_dir", "data/raw"),
            max_age_days=float(source.get("max_age_days", 7)),
            start_year=int(filters.get("start_year", 1990)),
            end_year=None if filters.get("end_year") is None else int(filters["end_year"]),
            baseline_year=int(data.get("baseline_year", 2005)),
            focus_countries=tuple(data.get("focus_countries", [])),
            max_null_share={k: float(v) for k, v in quality.get("max_null_share", {}).items()},
            per_capita_tolerance=float(quality.get("per_capita_tolerance", 0.02)),
            database=base / output.get("database", "output/emissions.db"),
            reports_dir=base / output.get("reports_dir", "output/reports"),
            config_hash=hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:12],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid config {path}: {exc}") from exc

    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    if cfg.end_year is not None and cfg.start_year > cfg.end_year:
        raise ConfigError("filters.start_year must be <= filters.end_year")
    if not cfg.start_year <= cfg.baseline_year:
        raise ConfigError("baseline_year must be >= filters.start_year")
    if cfg.end_year is not None and cfg.baseline_year > cfg.end_year:
        raise ConfigError("baseline_year must be <= filters.end_year")
    bad = [c for c in cfg.focus_countries if not ISO3.match(str(c))]
    if bad:
        raise ConfigError(f"focus_countries must be ISO alpha-3 codes, got: {bad}")
    for col, share in cfg.max_null_share.items():
        if not 0 <= share <= 1:
            raise ConfigError(f"quality.max_null_share.{col} must be between 0 and 1")
