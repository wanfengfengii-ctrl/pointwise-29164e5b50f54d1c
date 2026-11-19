import unittest

from lake.archive import Archive
from lake.audit.selection import audit_batch
from lake.read.collect import read_stripe
from lake.read.result import StripeUnavailable
from lake.volume.layout import SlotRole, make_stripe_address
from tests.support import fresh, offlined, seal_pair


class ColdReadTests(unittest.TestCase):
    def test_degraded_and_restored_volume(self):
        with fresh() as archive:
            address = seal_pair(archive)
            expected = read_stripe(archive, address)
            self.assertEqual((expected.values, expected.revision, expected.row_id), ((5, 9), 1, 'R03'))
            for role in SlotRole:
                with self.subTest(role=role), offlined(archive, role):
                    reopened = Archive.initialize(archive.root)
                    self.assertFalse(reopened.volume(role).path.exists())
                    self.assertEqual(read_stripe(reopened, address), expected)
                    self.assertEqual(audit_batch(reopened, 'L01').total, 14)
                self.assertEqual(read_stripe(archive, address), expected)
                self.assertEqual(audit_batch(archive, 'L01').total, 14)

    def test_zero_survivor(self):
        with fresh() as archive:
            address = seal_pair(archive, 0, 7)
            with offlined(archive, SlotRole.SECOND):
                result = read_stripe(archive, address)
                ledger = audit_batch(archive, 'L01')
            self.assertEqual(result.values, (0, 7))
            self.assertEqual(ledger.rows, (result,))
            self.assertEqual(ledger.total, 7)

    def test_unknown_stripe_raises(self):
        with fresh() as archive:
            seal_pair(archive)
            with self.assertRaises(StripeUnavailable):
                read_stripe(archive, make_stripe_address('L01', 1))
