"""Command-line entry point: ``python -m emissions_pipeline --config config/pipeline.yaml``."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import ConfigError, load_config
from .extract import ExtractError
from .pipeline import run
from .validate import DataQualityError, SchemaError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CO2 emissions ETL pipeline")
    parser.add_argument("--config", default="config/pipeline.yaml", help="path to the YAML config")
    parser.add_argument("--offline", action="store_true", help="use the cached raw file only")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("emissions_pipeline")

    try:
        cfg = load_config(args.config)
        result = run(cfg, offline=args.offline)
    except (ConfigError, ExtractError, SchemaError) as exc:
        log.error("%s", exc)
        return 2
    except DataQualityError as exc:
        log.error("%s (see quality_report.json)", exc)
        return 3

    log.info("Done. Run %s: %s", result.run_id, result.audit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
