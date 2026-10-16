import pytest

from emissions_pipeline.config import ConfigError, load_config


def test_loads_valid_config(config_file, tmp_path):
    cfg = load_config(config_file, base_dir=tmp_path)
    assert cfg.start_year == 2005 and cfg.end_year is None
    assert cfg.focus_countries == ("CAN", "BRA")
    assert cfg.database == tmp_path / "output/emissions.db"
    assert len(cfg.config_hash) == 12


def test_project_config_is_valid():
    cfg = load_config("config/pipeline.yaml")
    assert "CAN" in cfg.focus_countries


def test_hash_changes_with_content(config_file, tmp_path):
    h1 = load_config(config_file, tmp_path).config_hash
    config_file.write_text(config_file.read_text().replace("2005", "2006"))
    assert load_config(config_file, tmp_path).config_hash != h1


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("end_year: null", "end_year: 2000", "start_year must be <="),
        ("baseline_year: 2005", "baseline_year: 1990", "baseline_year must be >="),
        ("[CAN, BRA]", "[CAN, Brazil]", "ISO alpha-3"),
        ("co2_mt: 0.10", "co2_mt: 1.5", "between 0 and 1"),
        ("start_year: 2005", "start_year: soon", "Invalid config"),
    ],
)
def test_rejects_invalid_config(config_file, tmp_path, old, new, message):
    config_file.write_text(config_file.read_text().replace(old, new))
    with pytest.raises(ConfigError, match=message):
        load_config(config_file, tmp_path)


def test_missing_source_section(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("filters: {start_year: 2000}\n")
    with pytest.raises(ConfigError):
        load_config(bad, tmp_path)
