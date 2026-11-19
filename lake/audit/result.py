from dataclasses import dataclass

from lake.read.result import ReadResult


class AuditUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class AuditResult:
    batch_id: str
    rows: tuple[ReadResult, ...]
    total: int


def make_audit_result(batch_id, rows, total):
    return AuditResult(batch_id, tuple(rows), total)
