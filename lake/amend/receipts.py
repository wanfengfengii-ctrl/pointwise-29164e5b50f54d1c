from dataclasses import dataclass

from lake.amend.journal import RequestRecord
from lake.archive import Archive
from lake.volume.codec import decode_word
from lake.volume.layout import SlotRole, StripeAddress, valid_identifier


class ReceiptNotFound(LookupError):
    pass


@dataclass(frozen=True)
class CorrectionReceipt:
    request_id: str
    address: StripeAddress
    role: SlotRole
    new_value: int
    previous_revision: int
    revision: int


@dataclass(frozen=True)
class PendingReceipt:
    request_id: str
    address: StripeAddress
    previous_revision: int
    target_revision: int


def receipt_from_record(record: RequestRecord, bits):
    if not record.committed:
        return PendingReceipt(record.request_id, record.address, record.base_revision,
                              record.target_revision)
    return CorrectionReceipt(record.request_id, record.address, record.role,
                             decode_word(record.word, bits), record.base_revision, record.target_revision)


def get_receipt(archive: Archive, request_id):
    if not valid_identifier(request_id):
        raise ReceiptNotFound(request_id)
    record = archive.journal.get_request(request_id)
    if record is None:
        raise ReceiptNotFound(request_id)
    return receipt_from_record(record, archive.bits)
