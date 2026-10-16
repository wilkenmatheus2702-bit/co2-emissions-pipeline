import os
import time

import pytest

from emissions_pipeline import extract


def test_downloads_when_no_cache(tmp_path, raw_csv):
    res = extract.fetch(raw_csv.as_uri(), tmp_path / "cache", max_age_days=7)
    assert res.downloaded
    assert res.path.read_bytes() == raw_csv.read_bytes()
    assert res.sha256 == extract.sha256_of(raw_csv)


def test_reuses_fresh_cache(tmp_path, raw_csv):
    cache = tmp_path / "cache"
    extract.fetch(raw_csv.as_uri(), cache, max_age_days=7)
    res = extract.fetch(raw_csv.as_uri(), cache, max_age_days=7)
    assert not res.downloaded


def test_redownloads_stale_cache(tmp_path, raw_csv):
    cache = tmp_path / "cache"
    first = extract.fetch(raw_csv.as_uri(), cache, max_age_days=7)
    ten_days_ago = time.time() - 10 * 86400
    os.utime(first.path, (ten_days_ago, ten_days_ago))
    assert extract.fetch(raw_csv.as_uri(), cache, max_age_days=7).downloaded


def test_offline_uses_stale_cache(tmp_path, raw_csv):
    cache = tmp_path / "cache"
    first = extract.fetch(raw_csv.as_uri(), cache, max_age_days=7)
    os.utime(first.path, (0, 0))
    raw_csv.unlink()  # upstream gone: offline must not try to fetch it
    assert not extract.fetch(raw_csv.as_uri(), cache, max_age_days=7, offline=True).downloaded


def test_offline_without_cache_fails(tmp_path, raw_csv):
    with pytest.raises(extract.ExtractError, match="Offline"):
        extract.fetch(raw_csv.as_uri(), tmp_path / "cache", max_age_days=7, offline=True)


def test_failed_download_leaves_no_partial_file(tmp_path):
    cache = tmp_path / "cache"
    missing = (tmp_path / "nope.csv").as_uri()
    with pytest.raises(extract.ExtractError):
        extract.fetch(missing, cache, max_age_days=7)
    assert list(cache.iterdir()) == []


def test_read_raw_keeps_missing_iso_as_missing(raw_csv):
    df = extract.read_raw(raw_csv)
    assert df.loc[df["country"] == "World", "iso_code"].isna().all()
