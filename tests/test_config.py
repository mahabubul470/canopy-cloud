"""Tests for configuration file support."""

from pathlib import Path

from canopy.config import CanopyConfig, load_config


class TestCanopyConfig:
    def test_defaults(self) -> None:
        config = CanopyConfig()
        assert config.alpha == 0.5
        assert config.beta == 0.5
        assert config.budget_hourly_usd == 1.0
        assert config.carbon_hourly_gco2 == 100.0
        assert config.provider == "aws"
        assert config.regions == []
        assert config.idle_cpu_threshold == 2.0
        assert config.rightsize_cpu_threshold == 15.0

    def test_custom_values(self) -> None:
        config = CanopyConfig(
            alpha=0.7,
            beta=0.3,
            budget_hourly_usd=2.5,
            provider="gcp",
            regions=["us-west-2", "eu-north-1"],
            idle_cpu_threshold=5.0,
        )
        assert config.alpha == 0.7
        assert config.provider == "gcp"
        assert len(config.regions) == 2
        assert config.idle_cpu_threshold == 5.0


class TestLoadConfig:
    def test_load_from_explicit_path(self, tmp_path: Path) -> None:
        config_file = tmp_path / "canopy.yaml"
        config_file.write_text("alpha: 0.8\nbeta: 0.2\nbudget_hourly_usd: 5.0\nprovider: gcp\n")
        config = load_config(path=config_file)
        assert config.alpha == 0.8
        assert config.beta == 0.2
        assert config.budget_hourly_usd == 5.0
        assert config.provider == "gcp"

    def test_load_defaults_when_no_file(self, tmp_path: Path, monkeypatch: object) -> None:
        import canopy.config as config_mod

        monkeypatch.setattr(  # type: ignore[attr-defined]
            config_mod,
            "_SEARCH_PATHS",
            [tmp_path / "nonexistent.yaml"],
        )
        config = load_config()
        assert config.alpha == 0.5
        assert config.provider == "aws"

    def test_load_empty_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "canopy.yaml"
        config_file.write_text("")
        config = load_config(path=config_file)
        assert config.alpha == 0.5

    def test_load_with_regions(self, tmp_path: Path) -> None:
        config_file = tmp_path / "canopy.yaml"
        config_file.write_text("regions:\n  - us-east-1\n  - eu-west-1\n")
        config = load_config(path=config_file)
        assert config.regions == ["us-east-1", "eu-west-1"]

    def test_load_partial_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "canopy.yaml"
        config_file.write_text("idle_cpu_threshold: 3.0\n")
        config = load_config(path=config_file)
        assert config.idle_cpu_threshold == 3.0
        assert config.alpha == 0.5  # default preserved
