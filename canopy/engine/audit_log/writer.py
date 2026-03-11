"""Audit log writer — appends JSON Lines to date-partitioned files."""

from datetime import datetime
from pathlib import Path

from canopy.models.audit_log import ActionType, AuditEntry


class AuditLogWriter:
    """Appends audit entries as JSON Lines to ~/.config/canopy/audit-log/."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or (Path.home() / ".config" / "canopy" / "audit-log")

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _ensure_dir(self) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _log_path(self, dt: datetime) -> Path:
        return self._base_dir / f"{dt.strftime('%Y-%m-%d')}.jsonl"

    def write(self, entry: AuditEntry) -> Path:
        """Append a single audit entry. Returns the file path written to."""
        self._ensure_dir()
        path = self._log_path(entry.timestamp)
        line = entry.model_dump_json() + "\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
        return path

    def log_action(
        self,
        action: ActionType,
        *,
        workload_id: str | None = None,
        workload_name: str | None = None,
        provider: str | None = None,
        region: str | None = None,
        details: dict[str, object] | None = None,
        user: str | None = None,
        dry_run: bool = False,
    ) -> AuditEntry:
        """Create and write an audit entry in one call."""
        entry = AuditEntry(
            action=action,
            workload_id=workload_id,
            workload_name=workload_name,
            provider=provider,
            region=region,
            details=details or {},
            user=user,
            dry_run=dry_run,
        )
        self.write(entry)
        return entry
