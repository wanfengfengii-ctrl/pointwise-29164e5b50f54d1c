import unittest
from dataclasses import replace

from lake.amend.apply import apply_correction
from lake.amend.requests import CorrectionRequest
from lake.audit.reconcile import reconcile_correction
from lake.audit.result import AuditUnavailable
from lake.audit.selection import audit_batch
from lake.batch.intake import make_batch_input
from lake.batch.seal import seal_batch
from lake.read.collect import read_stripe
from lake.volume.layout import SlotRole
from tests.support import fresh, remove_block, seal_pair


class AuditTests(unittest.TestCase):
    def test_audit_reports_exact_original_order(self):
        with fresh() as archive:
            seal_batch(archive, make_batch_input('L01', [('R20', 0, 7), ('R03', 5, 9)]))
            ledger = audit_batch(archive, 'L01')
            self.assertEqual([(row.row_id, row.values, row.revision) for row in ledger.rows],
                             [('R20', (0, 7), 1), ('R03', (5, 9), 1)])
            self.assertEqual(ledger.total, 21)

    def test_required_stripe_prevents_partial_success(self):
        with fresh() as archive:
            sealed = seal_batch(archive, make_batch_input('L01', [('R20', 0, 7), ('R03', 5, 9)]))
            first, second = sealed.members
            self.assertEqual(audit_batch(archive, 'L01').total, 21)
            for role in (SlotRole.FIRST, SlotRole.SECOND):
                remove_block(archive, second.address, role)
            self.assertEqual(read_stripe(archive, first.address).values, (0, 7))
            with self.assertRaises(AuditUnavailable):
                audit_batch(archive, 'L01')

    def test_wide_total(self):
        with fresh() as archive:
            seal_pair(archive, 200, 100)
            ledger = audit_batch(archive, 'L01')
            self.assertEqual(ledger.rows[0].values, (200, 100))
            self.assertEqual(ledger.total, 300)

    def test_reconcile_checks_receipt_and_other_rows(self):
        with fresh() as archive:
            sealed = seal_batch(archive, make_batch_input('L01', [('R20', 0, 7), ('R03', 5, 9)]))
            first, second = sealed.members
            before = audit_batch(archive, 'L01')
            receipt = apply_correction(archive, CorrectionRequest('C01', second.address, SlotRole.SECOND, 13))
            after = audit_batch(archive, 'L01')
            self.assertEqual(after.total, 25)
            self.assertEqual(reconcile_correction(before, after, receipt), 4)
            with self.assertRaises(AuditUnavailable):
                reconcile_correction(before, after, replace(receipt, revision=3))
            with self.assertRaises(AuditUnavailable):
                reconcile_correction(before, replace(after, total=26), receipt)
            apply_correction(archive, CorrectionRequest('C02', first.address, SlotRole.FIRST, 1))
            with self.assertRaises(AuditUnavailable):
                reconcile_correction(before, audit_batch(archive, 'L01'), receipt)
