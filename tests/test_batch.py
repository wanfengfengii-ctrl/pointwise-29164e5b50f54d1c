import unittest

from lake.archive import Archive
from lake.audit.result import AuditUnavailable
from lake.audit.selection import audit_batch
from lake.batch.intake import make_batch_input
from lake.batch.manifest import BatchAlreadyExists
from lake.batch.seal import SealIncomplete, seal_batch
from lake.batch.validation import InvalidBatch
from lake.read.collect import read_stripe
from lake.read.result import StripeUnavailable
from lake.volume.codec import InvalidWord, decode_word, encode_word
from lake.volume.layout import SlotRole, make_stripe_address, slot_addresses
from lake.volume.slots import SlotUnavailable, read_slot
from tests.support import fresh, offlined


class BatchTests(unittest.TestCase):
    def test_seal_preserves_fixed_addresses_and_original_order(self):
        with fresh() as archive:
            rows = [('R20', 0, 7), ('R03', 5, 9)]
            receipt = seal_batch(archive, make_batch_input('L01', rows))
            second = seal_batch(archive, make_batch_input('L02', rows))
            self.assertEqual([member.row_id for member in receipt.members], ['R20', 'R03'])
            self.assertEqual([member.address.ordinal for member in receipt.members], [0, 1])
            self.assertNotEqual(receipt.members[0].address, second.members[0].address)
            reopened = Archive.open(archive.root)
            manifest = reopened.manifest.lookup_batch('L01')
            self.assertEqual(manifest.members, receipt.members)
            for member, expected in zip(manifest.members, ((0, 7, 7), (5, 9, 12)), strict=True):
                self.assertEqual(reopened.manifest.lookup_stripe(member.address), member)
                blocks = [read_slot(reopened, slot) for slot in slot_addresses(member.address)]
                self.assertEqual(tuple(block.value for block in blocks), expected)
                self.assertEqual([block.revision for block in blocks], [1, 1, 1])
            with self.assertRaises(BatchAlreadyExists):
                seal_batch(reopened, make_batch_input('L01', [('R20', 8, 8)]))
            self.assertEqual(read_stripe(reopened, receipt.members[0].address).values, (0, 7))

    def test_incomplete_stripe_cannot_be_sealed(self):
        with fresh() as archive:
            batch = make_batch_input('L01', [('R03', 5, 9)])
            address = make_stripe_address('L01', 0)
            with offlined(archive, SlotRole.PARITY):
                with self.assertRaises(SealIncomplete):
                    seal_batch(archive, batch)
            first, second, parity = slot_addresses(address)
            self.assertEqual(read_slot(archive, first).value, 5)
            self.assertEqual(read_slot(archive, second).value, 9)
            with self.assertRaises(SlotUnavailable):
                read_slot(archive, parity)
            self.assertIsNone(archive.manifest.lookup_batch('L01'))
            self.assertIsNone(archive.manifest.lookup_stripe(address))
            with self.assertRaises(StripeUnavailable):
                read_stripe(archive, address)
            with self.assertRaises(AuditUnavailable):
                audit_batch(archive, 'L01')

    def test_invalid_out_of_width_is_rejected_before_any_write(self):
        with fresh() as archive:
            address = make_stripe_address('L01', 0)
            cases = [[], [('R20', 0, 7), ('R03', 256, 9)], [('R03', -1, 9)],
                     [('R03', True, 9)], [('R03', None, 9)], [('R03', 5.0, 9)],
                     [('R03', 1, 2), ('R03', 3, 4)], [('bad row', 1, 2)]]
            for rows in cases:
                with self.subTest(rows=rows), self.assertRaises(InvalidBatch):
                    seal_batch(archive, make_batch_input('L01', rows))
                self.assertIsNone(archive.manifest.lookup_batch('L01'))
                for slot in slot_addresses(address):
                    with self.assertRaises(SlotUnavailable):
                        read_slot(archive, slot)
            with self.assertRaises(InvalidBatch):
                seal_batch(archive, make_batch_input('bad batch', [('R03', 0, 9)]))
            receipt = seal_batch(archive, make_batch_input('L01', [('R03', 0, 9)]))
            self.assertEqual(read_stripe(archive, receipt.members[0].address).values, (0, 9))

    def test_nonbyte_width_and_padding(self):
        self.assertEqual(encode_word(511, 9), b'\x01\xff')
        self.assertEqual(decode_word(b'\x01\xff', 9), 511)
        for illegal in (b'\x02\x00', b'\x01'):
            with self.assertRaises(InvalidWord):
                decode_word(illegal, 9)
        with fresh(bits=9) as archive:
            receipt = seal_batch(archive, make_batch_input('N01', [('R03', 256, 255)]))
            address = receipt.members[0].address
            with offlined(archive, SlotRole.FIRST):
                self.assertEqual(read_stripe(archive, address).values, (256, 255))
