from lake.amend.receipts import CorrectionReceipt
from lake.audit.result import AuditResult, AuditUnavailable
from lake.audit.totals import sum_observations
from lake.batch.manifest import BatchManifest
from lake.read.result import ReadResult
from lake.volume.layout import SlotRole


def _identity(row):
    return row.address, row.row_id


def match_members(manifest: BatchManifest, rows: tuple[ReadResult, ...]):
    expected = tuple(map(_identity, manifest.members))
    observed = tuple(map(_identity, rows))
    if observed != expected:
        raise AuditUnavailable(f'collected rows differ from sealed membership of {manifest.batch_id}')


def _check_ledger(ledger):
    if not ledger.rows or ledger.total != sum_observations(ledger.rows):
        raise AuditUnavailable('ledger total cannot be verified')
    for ordinal, row in enumerate(ledger.rows):
        if row.address.batch_id != ledger.batch_id or row.address.ordinal != ordinal:
            raise AuditUnavailable('ledger membership is not in original order')


def reconcile_correction(before: AuditResult, after: AuditResult, receipt: CorrectionReceipt):
    if not isinstance(receipt, CorrectionReceipt):
        raise AuditUnavailable('reconciliation requires an effective correction receipt')
    if before.batch_id != after.batch_id or receipt.address.batch_id != before.batch_id:
        raise AuditUnavailable('ledger and correction do not name the same batch')
    _check_ledger(before)
    _check_ledger(after)
    if tuple(map(_identity, before.rows)) != tuple(map(_identity, after.rows)):
        raise AuditUnavailable('ledger membership changed')
    ordinal = receipt.address.ordinal
    if ordinal >= len(before.rows):
        raise AuditUnavailable('correction row is absent from the ledger')
    old, new = before.rows[ordinal], after.rows[ordinal]
    if (old.revision, new.revision) != (receipt.previous_revision, receipt.revision):
        raise AuditUnavailable('ledger revisions differ from the correction receipt')
    if receipt.role not in (SlotRole.FIRST, SlotRole.SECOND):
        raise AuditUnavailable('receipt must target an observation')
    index = 0 if receipt.role == SlotRole.FIRST else 1
    if new.values[index] != receipt.new_value or new.values[1 - index] != old.values[1 - index]:
        raise AuditUnavailable('target observations do not agree with the correction')
    for position, (old_row, new_row) in enumerate(zip(before.rows, after.rows, strict=True)):
        if position != ordinal and old_row != new_row:
            raise AuditUnavailable('a second ledger row changed')
    delta = new.values[index] - old.values[index]
    if delta != after.total - before.total:
        raise AuditUnavailable('ledger and correction deltas disagree')
    return delta
