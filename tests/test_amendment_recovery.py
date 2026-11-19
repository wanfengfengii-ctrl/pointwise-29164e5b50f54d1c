import unittest

from lake.amend.apply import apply_correction, resume_correction
from lake.amend.journal import RequestConflict
from lake.amend.receipts import CorrectionReceipt, PendingReceipt, ReceiptNotFound, get_receipt
from lake.amend.requests import CorrectionRequest
from lake.archive import Archive, ArchiveConfigurationError
from lake.audit.reconcile import reconcile_correction
from lake.audit.selection import audit_batch
from lake.read.collect import read_stripe
from lake.volume.layout import SlotRole, slot_addresses
from lake.volume.slots import read_slot
from tests.support import EXIT_CODES, fresh, offlined, seal_pair, terminate_at


class AmendmentRecoveryTests(unittest.TestCase):
    def test_restart_after_first_slot_and_resume(self):
        with fresh() as archive:
            address = seal_pair(archive)
            baseline = audit_batch(archive, 'L01')
            child = terminate_at(archive, 'after_slot')
            self.assertEqual(child.returncode, EXIT_CODES['after_slot'], child.stderr)
            reopened = Archive.open(archive.root)
            pending = PendingReceipt('C01', address, 1, 2)
            self.assertEqual(get_receipt(reopened, 'C01'), pending)
            with offlined(reopened, SlotRole.SECOND):
                old = read_stripe(reopened, address)
                self.assertEqual((old.revision, old.values), (1, (5, 9)))
                self.assertEqual(audit_batch(reopened, 'L01'), baseline)
            request = CorrectionRequest('C01', address, SlotRole.FIRST, 6)
            receipt = apply_correction(reopened, request)
            self.assertEqual(receipt, CorrectionReceipt('C01', address, SlotRole.FIRST, 6, 1, 2))
            self.assertEqual(resume_correction(reopened, 'C01'), receipt)
            self.assertEqual(get_receipt(reopened, 'C01'), receipt)
            final = audit_batch(reopened, 'L01')
            self.assertEqual((final.rows[0].values, final.total), ((6, 9), 15))
            self.assertEqual(reconcile_correction(baseline, final, receipt), 1)

    def test_atomic_block_before_and_after_commit(self):
        for phase, first in (('before_slot', (1, 5)), ('after_slot', (2, 6))):
            with self.subTest(phase=phase), fresh() as archive:
                address = seal_pair(archive)
                child = terminate_at(archive, phase)
                self.assertEqual(child.returncode, EXIT_CODES[phase], child.stderr)
                reopened = Archive.open(archive.root)
                blocks = [read_slot(reopened, slot) for slot in slot_addresses(address)]
                self.assertEqual([(block.revision, block.value) for block in blocks],
                                 [first, (1, 9), (1, 12)])
                self.assertEqual(read_stripe(reopened, address).values, (5, 9))
                written = []

                def observe(event):
                    if event.phase == 'after_slot':
                        written.append(event.role)

                receipt = resume_correction(Archive.open(archive.root, on_event=observe), 'C01')
                expected = list(SlotRole) if phase == 'before_slot' else [SlotRole.SECOND, SlotRole.PARITY]
                self.assertEqual(written, expected)
                self.assertEqual(receipt.revision, 2)
                self.assertEqual(read_stripe(reopened, address).values, (6, 9))

    def test_repeat_initialization_preserves_published_state(self):
        with fresh() as archive:
            address = seal_pair(archive)
            manifest = archive.manifest.lookup_batch('L01')
            request = CorrectionRequest('C01', address, SlotRole.FIRST, 6)
            receipt = apply_correction(archive, request)
            reopened = Archive.initialize(archive.root, bits=8)
            self.assertEqual(reopened.manifest.lookup_batch('L01'), manifest)
            self.assertEqual(get_receipt(reopened, 'C01'), receipt)
            self.assertEqual(audit_batch(reopened, 'L01').total, 15)
            with self.assertRaises(ArchiveConfigurationError):
                Archive.initialize(archive.root, bits=9)
            self.assertEqual(read_stripe(Archive.open(archive.root), address).values, (6, 9))

    def test_lost_reply_redelivers_original_receipt(self):
        with fresh() as archive:
            address = seal_pair(archive)
            child = terminate_at(archive, 'after_publish')
            self.assertEqual(child.returncode, EXIT_CODES['after_publish'], child.stderr)
            events = []
            reopened = Archive.open(archive.root, on_event=events.append)
            request = CorrectionRequest('C01', address, SlotRole.FIRST, 6)
            original = get_receipt(reopened, 'C01')
            self.assertEqual(original, CorrectionReceipt('C01', address, SlotRole.FIRST, 6, 1, 2))
            self.assertEqual(apply_correction(reopened, request), original)
            self.assertEqual(apply_correction(reopened, request), original)
            self.assertEqual(events, [])
            self.assertEqual(read_stripe(reopened, address).values, (6, 9))
            with self.assertRaises(ReceiptNotFound):
                get_receipt(reopened, 'unknown')

    def test_original_after_later_correction(self):
        with fresh() as archive:
            address = seal_pair(archive)
            child = terminate_at(archive, 'after_publish')
            self.assertEqual(child.returncode, EXIT_CODES['after_publish'], child.stderr)
            original = CorrectionReceipt('C01', address, SlotRole.FIRST, 6, 1, 2)
            later = apply_correction(Archive.open(archive.root),
                                     CorrectionRequest('C02', address, SlotRole.FIRST, 7))
            reopened = Archive.open(archive.root)
            self.assertEqual(later.revision, 3)
            self.assertEqual(get_receipt(reopened, 'C01'), original)
            self.assertEqual(apply_correction(reopened, CorrectionRequest('C01', address, SlotRole.FIRST, 6)),
                             original)
            row = read_stripe(reopened, address)
            self.assertEqual((row.revision, row.values), (3, (7, 9)))
            self.assertEqual(audit_batch(reopened, 'L01').total, 16)

    def test_conflict_checks_binding_before_returning_terminal_result(self):
        with fresh() as archive:
            address = seal_pair(archive)
            request = CorrectionRequest('C01', address, SlotRole.FIRST, 6)
            receipt = apply_correction(archive, request)
            reopened = Archive.open(archive.root)
            for different in (CorrectionRequest('C01', address, SlotRole.FIRST, 8),
                              CorrectionRequest('C01', address, SlotRole.SECOND, 6)):
                with self.assertRaises(RequestConflict):
                    apply_correction(reopened, different)
            self.assertEqual(get_receipt(reopened, 'C01'), receipt)
            self.assertEqual(read_stripe(reopened, address).values, (6, 9))
            self.assertEqual(audit_batch(reopened, 'L01').total, 15)
