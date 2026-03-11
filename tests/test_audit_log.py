"""Tests for audit log writer and reader."""

from datetime import date, datetime
from pathlib import Path

import pytest

from canopy.engine.audit_log.reader import AuditLogReader
from canopy.engine.audit_log.writer import AuditLogWriter
from canopy.models.audit_log import ActionType, AuditEntry


@pytest.fixture()
def log_dir(tmp_path: Path) -> Path:
    return tmp_path / "audit-log"


@pytest.fixture()
def writer(log_dir: Path) -> AuditLogWriter:
    return AuditLogWriter(base_dir=log_dir)


@pytest.fixture()
def reader(log_dir: Path) -> AuditLogReader:
    return AuditLogReader(base_dir=log_dir)


class TestAuditEntry:
    def test_create_entry(self) -> None:
        entry = AuditEntry(
            action=ActionType.AUDIT_RUN,
            provider="aws",
            region="us-east-1",
        )
        assert entry.action == ActionType.AUDIT_RUN
        assert entry.provider == "aws"
        assert entry.dry_run is False

    def test_entry_with_details(self) -> None:
        entry = AuditEntry(
            action=ActionType.APPLY_COMPLETED,
            workload_id="i-123",
            workload_name="web-server",
            details={"type": "rightsize", "from": "m5.xlarge", "to": "m5.large"},
        )
        assert entry.details["type"] == "rightsize"
        assert entry.workload_id == "i-123"

    def test_all_action_types(self) -> None:
        for action in ActionType:
            entry = AuditEntry(action=action)
            assert entry.action == action

    def test_roundtrip_json(self) -> None:
        entry = AuditEntry(
            action=ActionType.CARL_DECISION,
            workload_id="i-456",
            details={"strategy": "defer"},
        )
        json_str = entry.model_dump_json()
        restored = AuditEntry.model_validate_json(json_str)
        assert restored.action == entry.action
        assert restored.workload_id == entry.workload_id


class TestAuditLogWriter:
    def test_write_creates_dir(self, writer: AuditLogWriter, log_dir: Path) -> None:
        entry = AuditEntry(action=ActionType.AUDIT_RUN, provider="aws")
        writer.write(entry)
        assert log_dir.is_dir()

    def test_write_creates_jsonl(self, writer: AuditLogWriter, log_dir: Path) -> None:
        entry = AuditEntry(action=ActionType.AUDIT_RUN)
        path = writer.write(entry)
        assert path.suffix == ".jsonl"
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_write_appends(self, writer: AuditLogWriter) -> None:
        e1 = AuditEntry(action=ActionType.AUDIT_RUN)
        e2 = AuditEntry(action=ActionType.APPLY_STARTED, workload_id="i-1")
        path = writer.write(e1)
        writer.write(e2)
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_log_action_shortcut(self, writer: AuditLogWriter) -> None:
        entry = writer.log_action(
            ActionType.APPLY_COMPLETED,
            workload_id="i-789",
            provider="aws",
            details={"status": "success"},
        )
        assert entry.action == ActionType.APPLY_COMPLETED
        assert entry.workload_id == "i-789"

    def test_date_partitioned_filename(self, writer: AuditLogWriter) -> None:
        entry = AuditEntry(action=ActionType.AUDIT_RUN)
        path = writer.write(entry)
        today = datetime.now().strftime("%Y-%m-%d")
        assert path.name == f"{today}.jsonl"


class TestAuditLogReader:
    def test_read_empty(self, reader: AuditLogReader) -> None:
        entries = reader.read_date(date.today())
        assert entries == []

    def test_read_written_entries(self, writer: AuditLogWriter, reader: AuditLogReader) -> None:
        writer.log_action(ActionType.AUDIT_RUN, provider="aws")
        writer.log_action(ActionType.APPLY_STARTED, workload_id="i-1")

        entries = reader.read_date(date.today())
        assert len(entries) == 2
        assert entries[0].action == ActionType.AUDIT_RUN
        assert entries[1].action == ActionType.APPLY_STARTED

    def test_query_by_action(self, writer: AuditLogWriter, reader: AuditLogReader) -> None:
        writer.log_action(ActionType.AUDIT_RUN)
        writer.log_action(ActionType.APPLY_STARTED, workload_id="i-1")
        writer.log_action(ActionType.APPLY_COMPLETED, workload_id="i-1")

        results = reader.query(
            date.today(),
            date.today(),
            action=ActionType.APPLY_STARTED,
        )
        assert len(results) == 1
        assert results[0].workload_id == "i-1"

    def test_query_by_workload(self, writer: AuditLogWriter, reader: AuditLogReader) -> None:
        writer.log_action(ActionType.APPLY_STARTED, workload_id="i-1")
        writer.log_action(ActionType.APPLY_STARTED, workload_id="i-2")
        writer.log_action(ActionType.APPLY_COMPLETED, workload_id="i-1")

        results = reader.query(
            date.today(),
            date.today(),
            workload_id="i-1",
        )
        assert len(results) == 2

    def test_latest(self, writer: AuditLogWriter, reader: AuditLogReader) -> None:
        for i in range(5):
            writer.log_action(ActionType.AUDIT_RUN, details={"i": i})

        latest = reader.latest(count=3)
        assert len(latest) == 3

    def test_read_range_single_day(self, writer: AuditLogWriter, reader: AuditLogReader) -> None:
        writer.log_action(ActionType.AUDIT_RUN)
        entries = reader.read_range(date.today(), date.today())
        assert len(entries) == 1
