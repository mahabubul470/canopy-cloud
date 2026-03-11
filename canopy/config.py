"""Configuration file support for Canopy."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class CanopyConfig(BaseModel):
    """Canopy configuration loaded from canopy.yaml."""

    alpha: float = Field(default=0.5, ge=0, le=1, description="Cost weight")
    beta: float = Field(default=0.5, ge=0, le=1, description="Carbon weight")
    budget_hourly_usd: float = Field(default=1.0, gt=0)
    carbon_hourly_gco2: float = Field(default=100.0, gt=0)
    provider: str = "aws"
    regions: list[str] = Field(default_factory=list)
    idle_cpu_threshold: float = Field(default=2.0, ge=0, le=100)
    rightsize_cpu_threshold: float = Field(default=15.0, ge=0, le=100)
    # Phase 3 — agentic orchestration
    audit_log_dir: str | None = None
    approval_channel: str | None = None
    slack_webhook_url: str | None = None
    github_token: str | None = None
    github_repo: str | None = None
    carl_urgency: str = "normal"
    dashboard_port: int = Field(default=8080, ge=1, le=65535)


_SEARCH_PATHS = [
    Path("canopy.yaml"),
    Path.home() / ".config" / "canopy" / "canopy.yaml",
]


def load_config(path: Path | None = None) -> CanopyConfig:
    """Load configuration from a YAML file.

    Search order:
    1. Explicit path (if provided)
    2. ./canopy.yaml
    3. ~/.config/canopy/canopy.yaml
    4. Defaults
    """
    if path is not None:
        return _parse_config(path)

    for candidate in _SEARCH_PATHS:
        if candidate.is_file():
            return _parse_config(candidate)

    return CanopyConfig()


def _parse_config(path: Path) -> CanopyConfig:
    """Parse a YAML config file into a CanopyConfig."""
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return CanopyConfig()
    return CanopyConfig(**data)
