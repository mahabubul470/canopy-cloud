"""Audit log reader — queries JSON Lines audit log files."""

from datetime import date, datetime, timedelta
from pathlib import Path

from canopy.models.audit_log import ActionType, AuditEntry


class AuditLogReader:
    """Reads and queries audit log entries from date-partitioned JSONL files."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or (Path.home() / ".config" / "canopy" / "audit-log")

    def _log_path(self, dt: date) -> Path:
        return self._base_dir / f"{dt.strftime('%Y-%m-%d')}.jsonl"

    def _read_file(self, path: Path) -> list[AuditEntry]:
        """Read all entries from a single JSONL file."""
        if not path.is_file():
            return []
        entries: list[AuditEntry] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                entries.append(AuditEntry.model_validate_json(stripped))
        return entries

    def read_date(self, dt: date) -> list[AuditEntry]:
        """Read all entries for a specific date."""
        return self._read_file(self._log_path(dt))

    def read_range(self, start: date, end: date) -> list[AuditEntry]:
        """Read entries for a date range (inclusive)."""
        entries: list[AuditEntry] = []
        current = start
        while current <= end:
            entries.extend(self._read_file(self._log_path(current)))
            current = current + timedelta(days=1)
        return entries

    def query(
        self,
        start: date,
        end: date,
        *,
        action: ActionType | None = None,
        workload_id: str | None = None,
    ) -> list[AuditEntry]:
        """Query entries by date range and optional filters."""
        entries = self.read_range(start, end)
        if action is not None:
            entries = [e for e in entries if e.action == action]
        if workload_id is not None:
            entries = [e for e in entries if e.workload_id == workload_id]
        return entries

    def latest(self, count: int = 10) -> list[AuditEntry]:
        """Read the latest N entries from today's log."""
        entries = self.read_date(datetime.now().date())
        return entries[-count:]
