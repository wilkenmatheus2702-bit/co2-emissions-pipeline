"""Extract step: download the raw CSV with a local cache and a checksum."""

from __future__ import annotations

import hashlib
import logging
import shutil
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


class ExtractError(RuntimeError):
    """Raised when the raw file cannot be obtained."""


@dataclass(frozen=True)
class ExtractResult:
    path: Path
    sha256: str
    downloaded: bool


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, cache_dir: Path, max_age_days: float, offline: bool = False) -> ExtractResult:
    """Return a local copy of ``url``, downloading it only when needed.

    The cached file is reused when it is younger than ``max_age_days``.
    With ``offline=True`` the cache is always used and no request is made.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / Path(url.split("?")[0]).name

    if target.exists():
        age_days = (time.time() - target.stat().st_mtime) / 86400
        if offline or age_days < max_age_days:
            log.info("Using cached file %s (%.1f days old)", target, age_days)
            return ExtractResult(target, sha256_of(target), downloaded=False)
    elif offline:
        raise ExtractError(f"Offline mode but no cached file at {target}")

    log.info("Downloading %s", url)
    tmp = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as resp, tmp.open("wb") as out:
            shutil.copyfileobj(resp, out)
    except Exception as exc:  # network errors vary by platform
        tmp.unlink(missing_ok=True)
        raise ExtractError(f"Download failed for {url}: {exc}") from exc
    tmp.replace(target)  # atomic: never leave a half-written cache file
    return ExtractResult(target, sha256_of(target), downloaded=True)


def read_raw(path: Path) -> pd.DataFrame:
    """Read the raw CSV. ``iso_code`` is kept as text so empty values stay missing."""
    return pd.read_csv(path, dtype={"iso_code": "string", "country": "string"})
