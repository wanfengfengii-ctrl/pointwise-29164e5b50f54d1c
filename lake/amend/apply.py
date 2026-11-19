from lake.amend.handoff import OverwriteUnavailable, plan_overwrite
from lake.amend.receipts import ReceiptNotFound, receipt_from_record
from lake.amend.requests import CorrectionRequest, InvalidCorrection, normalize_request
from lake.archive import Archive
from lake.read.collect import read_stripe
from lake.read.result import StripeUnavailable
from lake.volume.codec import decode_word
from lake.volume.layout import slot_addresses, valid_identifier
from lake.volume.slots import SlotUnavailable, write_slot


class CorrectionIncomplete(RuntimeError):
    pass


def _write_target(archive, journal, record, words):
    for slot, word in zip(slot_addresses(record.address), words, strict=True):
        archive.notify('before_slot', record.address, record.target_revision, slot.role)
        with journal.pending_write(record) as db:
            if db is None:
                return
            written = write_slot(archive, slot, record.target_revision, word)
        if written:
            archive.notify('after_slot', record.address, record.target_revision, slot.role)


def apply_correction(archive: Archive, request: CorrectionRequest):
    request = normalize_request(request, archive.bits)
    if archive.manifest.lookup_stripe(request.address) is None:
        raise InvalidCorrection('correction requires a sealed stripe')
    journal = archive.journal
    record = journal.register(request, archive.bits)
    if record.committed:
        return receipt_from_record(record, archive.bits)

    def read_base():
        result = read_stripe(archive, request.address, observe=False)
        return result.revision, result.values

    try:
        words = plan_overwrite(journal, record, archive.bits, read_base)
        if words is not None:
            _write_target(archive, journal, record, words)
    except (StripeUnavailable, OverwriteUnavailable, SlotUnavailable) as exc:
        raise CorrectionIncomplete(f'correction {request.request_id} remains pending') from exc
    completed, published = journal.commit_effective(record)
    if published:
        archive.notify('after_publish', completed.address, completed.target_revision)
    return receipt_from_record(completed, archive.bits)


def resume_correction(archive: Archive, request_id):
    if not valid_identifier(request_id):
        raise ReceiptNotFound(request_id)
    record = archive.journal.get_request(request_id)
    if record is None:
        raise ReceiptNotFound(request_id)
    value = decode_word(record.word, archive.bits)
    return apply_correction(archive, CorrectionRequest(request_id, record.address, record.role, value))
