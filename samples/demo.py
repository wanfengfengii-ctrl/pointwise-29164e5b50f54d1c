import json
from pathlib import Path
from tempfile import TemporaryDirectory

from lake.amend.apply import apply_correction
from lake.amend.receipts import get_receipt
from lake.amend.requests import CorrectionRequest
from lake.archive import Archive
from lake.audit.reconcile import reconcile_correction
from lake.audit.selection import audit_batch
from lake.batch.intake import make_batch_input
from lake.batch.seal import seal_batch
from lake.read.collect import read_stripe
from lake.volume.layout import SlotRole


def _require_equal(actual, expected):
    if actual != expected:
        raise RuntimeError(f'expected {expected!r}, observed {actual!r}')


def main():
    sample = json.loads(Path(__file__).with_name('incoming.json').read_text(encoding='utf-8'))
    batch_id = sample['batch_id']
    correction = sample['correction']
    with TemporaryDirectory(prefix='luwan-demo-') as directory:
        archive = Archive.initialize(directory, bits=sample['bits'])
        sealed = seal_batch(archive, make_batch_input(batch_id, sample['rows']))
        members = {member.row_id: member.address for member in sealed.members}
        address = members[correction['row_id']]
        before = audit_batch(archive, batch_id)
        original = read_stripe(archive, address)
        during = []

        def read_during_write(event):
            if event.phase != 'after_slot' or event.role is not SlotRole.FIRST:
                return
            live = archive.volume(SlotRole.SECOND).path
            offline = live.with_suffix('.offline')
            live.rename(offline)
            try:
                during.append(audit_batch(archive, batch_id))
            finally:
                offline.rename(live)

        writer = Archive.open(directory, on_event=read_during_write)
        request = CorrectionRequest(correction['request_id'], address, SlotRole(correction['role']),
                                    correction['new_value'])
        receipt = apply_correction(writer, request)
        reopened = Archive.open(directory)
        _require_equal(get_receipt(reopened, request.request_id), receipt)
        _require_equal(apply_correction(reopened, request), receipt)
        after = audit_batch(reopened, batch_id)
        collected = read_stripe(reopened, address)
        delta = reconcile_correction(before, after, receipt)
        _require_equal(len(during), 1)
        _require_equal(during[0], before)
        _require_equal([row.row_id for row in after.rows], ['R20', 'R03'])
        _require_equal([row.values for row in after.rows], [(0, 7), (6, 9)])
        _require_equal((original.revision, collected.revision, receipt.revision), (1, 2, 2))
        expected = [[5, 9], [5, 9], [6, 9]]
        paused_row = next(row for row in during[0].rows if row.address == address)
        actual = [list(row.values) for row in (original, paused_row, collected)]
        downstream_expected = [21, 21, 22, 1]
        downstream_actual = [before.total, during[0].total, after.total, delta]
        _require_equal(actual, expected)
        _require_equal(downstream_actual, downstream_expected)
        print(f'{batch_id} {correction["row_id"]} {original.values} rev {original.revision} -> '
              f'{collected.values} rev {collected.revision}, receipt {receipt.request_id}')
        print(f'Day ledger {before.total} -> {after.total}, correction delta {delta}')
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'amend',
            'input': sample,
            'expected': expected,
            'actual': actual,
            'downstream_expected': downstream_expected,
            'downstream_actual': downstream_actual,
            'code_paths': ['lake/amend/apply.py', 'lake/read/collect.py', 'lake/audit/selection.py',
                           'lake/audit/reconcile.py'],
            'oracle': 'R20 contributes 0+7=7. R03 contributes 5+9=14 before publication and 6+9=15 after.',
        }, ensure_ascii=False))


if __name__ == '__main__':
    main()
