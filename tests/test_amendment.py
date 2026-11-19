import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from lake.amend.apply import CorrectionIncomplete, apply_correction, resume_correction
from lake.amend.journal import RequestConflict
from lake.amend.receipts import PendingReceipt, get_receipt
from lake.amend.requests import CorrectionRequest, InvalidCorrection
from lake.archive import Archive
from lake.audit.reconcile import reconcile_correction
from lake.audit.selection import audit_batch
from lake.read.collect import read_stripe
from lake.volume.layout import SlotRole, slot_addresses
from lake.volume.slots import read_slot
from tests.support import fresh, offlined, seal_pair


class AmendmentTests(unittest.TestCase):
    def test_half_write(self):
        with fresh() as archive:
            address = seal_pair(archive)
            baseline = audit_batch(archive, 'L01')
            self.assertEqual(baseline.total, 14)
            request = CorrectionRequest('C01', address, SlotRole.FIRST, 6)
            checked = []

            def pause(event):
                if event.phase == 'after_slot' and event.role is SlotRole.FIRST:
                    first, _, parity = slot_addresses(address)
                    first_block = read_slot(archive, first)
                    parity_block = read_slot(archive, parity)
                    self.assertEqual((first_block.revision, first_block.value), (2, 6))
                    self.assertEqual((parity_block.revision, parity_block.value), (1, 12))
                    with offlined(archive, SlotRole.SECOND):
                        old = read_stripe(archive, address)
                        self.assertEqual(old.values, (5, 9),
                                         f'STRIPE_MIXED_REV expected (5, 9), observed {old.values}')
                        self.assertEqual((old.revision, old.row_id), (1, 'R03'))
                        self.assertEqual(audit_batch(archive, 'L01'), baseline)
                    checked.append(old)

            writer = Archive.open(archive.root, on_event=pause)
            receipt = apply_correction(writer, request)
            self.assertEqual(len(checked), 1)
            self.assertEqual(get_receipt(archive, 'C01'), receipt)
            final = audit_batch(archive, 'L01')
            self.assertEqual((final.rows[0].values, final.rows[0].revision, final.total), ((6, 9), 2, 15))
            self.assertEqual(reconcile_correction(baseline, final, receipt), 1)

    def test_one_pending_and_online_before_publish(self):
        with fresh() as archive:
            address = seal_pair(archive)
            request = CorrectionRequest('C01', address, SlotRole.FIRST, 6)
            rival = CorrectionRequest('C02', address, SlotRole.SECOND, 8)
            observed = []

            def pause(event):
                if event.phase == 'after_slot' and event.role is SlotRole.FIRST:
                    with self.assertRaises(RequestConflict):
                        apply_correction(archive, rival)
                    self.assertEqual(get_receipt(archive, 'C01'), PendingReceipt('C01', address, 1, 2))
                    online = read_stripe(archive, address)
                    observed.append((online.revision, online.values))

            receipt = apply_correction(Archive.open(archive.root, on_event=pause), request)
            online = read_stripe(archive, address)
            self.assertEqual(observed, [(1, (5, 9))])
            self.assertEqual((online.revision, online.values), (2, (6, 9)))
            self.assertEqual(resume_correction(archive, request.request_id), receipt)

    def test_rotate_missing_volumes(self):
        with fresh() as archive:
            address = seal_pair(archive)
            seen = []

            def check(revision, pair, total):
                for role in SlotRole:
                    with self.subTest(revision=revision, role=role), offlined(archive, role):
                        result = read_stripe(archive, address)
                        self.assertEqual((result.revision, result.values), (revision, pair))
                        self.assertEqual(audit_batch(archive, 'L01').total, total)
                        seen.append((revision, role))

            def pause(event):
                if event.phase == 'after_slot' and event.role is SlotRole.FIRST:
                    check(1, (5, 9), 14)
                if event.phase == 'after_publish':
                    check(2, (6, 9), 15)

            request = CorrectionRequest('C01', address, SlotRole.FIRST, 6)
            apply_correction(Archive.open(archive.root, on_event=pause), request)
            check(2, (6, 9), 15)
            self.assertEqual(len(seen), 9)

    def test_cross_publish(self):
        with fresh() as archive:
            address = seal_pair(archive)
            pinned = Event()
            release = Event()

            def after_pin(event):
                if event.phase == 'after_pin':
                    self.assertEqual(event.revision, 1)
                    pinned.set()
                    if not release.wait(10):
                        raise AssertionError('reader did not receive release signal')

            reader = Archive.open(archive.root, on_event=after_pin)
            with ThreadPoolExecutor(max_workers=1) as pool:
                reading = pool.submit(read_stripe, reader, address)
                try:
                    self.assertTrue(pinned.wait(10))
                    request = CorrectionRequest('C01', address, SlotRole.FIRST, 6)
                    receipt = apply_correction(archive, request)
                    with offlined(archive, SlotRole.SECOND):
                        release.set()
                        observed = reading.result(timeout=10)
                finally:
                    release.set()
            self.assertEqual(observed.address, address)
            self.assertEqual(observed.row_id, 'R03')
            self.assertIn((observed.revision, observed.values), [(1, (5, 9)), (2, (6, 9))])
            self.assertEqual(read_stripe(archive, address).revision, receipt.revision)

    def test_ambiguous_old(self):
        physical = []
        for first, second in ((5, 9), (7, 11)):
            with self.subTest(old=(first, second)), fresh() as archive:
                address = seal_pair(archive, first, second)
                target = CorrectionRequest('C01', address, SlotRole.FIRST, 6)

                def pause(event):
                    if event.phase == 'after_slot' and event.role is SlotRole.FIRST:
                        a, _, p = slot_addresses(address)
                        physical.append((read_slot(archive, a).value, read_slot(archive, p).value))
                        with offlined(archive, SlotRole.SECOND):
                            old = read_stripe(archive, address)
                            self.assertEqual((old.revision, old.values), (1, (first, second)))
                            self.assertEqual(audit_batch(archive, 'L01').total, first + second)

                apply_correction(Archive.open(archive.root, on_event=pause), target)
                self.assertEqual(read_stripe(archive, address).values, (6, second))
        self.assertEqual(physical, [(6, 12), (6, 12)])

    def test_failed_target_write_leaves_pending_and_old_pair_readable(self):
        with fresh() as archive:
            address = seal_pair(archive)
            request = CorrectionRequest('C01', address, SlotRole.SECOND, 8)
            with offlined(archive, SlotRole.PARITY):
                with self.assertRaises(CorrectionIncomplete):
                    apply_correction(archive, request)
                self.assertEqual(get_receipt(archive, 'C01'), PendingReceipt('C01', address, 1, 2))
                self.assertEqual(read_stripe(archive, address).values, (5, 9))
            receipt = resume_correction(archive, 'C01')
            self.assertEqual((receipt.revision, read_stripe(archive, address).values), (2, (5, 8)))

    def test_value_wider_than_sqlite_integer(self):
        with fresh(bits=65) as archive:
            address = seal_pair(archive, 5, 9)
            value = 2**64 + 1
            request = CorrectionRequest('C01', address, SlotRole.FIRST, value)
            receipt = apply_correction(archive, request)
            self.assertEqual(receipt.new_value, value)
            with offlined(archive, SlotRole.FIRST):
                self.assertEqual(read_stripe(archive, address).values, (value, 9))
            with self.assertRaises(InvalidCorrection):
                apply_correction(archive, CorrectionRequest('C02', address, SlotRole.FIRST, 2**65))
            self.assertEqual(audit_batch(archive, 'L01').total, 2**64 + 10)
