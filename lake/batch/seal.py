from dataclasses import dataclass

from lake.archive import Archive
from lake.batch.intake import BatchInput
from lake.batch.manifest import BatchMember
from lake.batch.placement import place_rows
from lake.batch.validation import validate_intake
from lake.volume.layout import INITIAL_REVISION, slot_addresses
from lake.volume.parity import stripe_words
from lake.volume.slots import SlotUnavailable, write_slot


class SealIncomplete(RuntimeError):
    pass


@dataclass(frozen=True)
class SealReceipt:
    batch_id: str
    members: tuple[BatchMember, ...]


def seal_batch(archive: Archive, batch: BatchInput):
    validate_intake(batch, archive.bits)
    placed = place_rows(batch)
    manifest = archive.manifest
    manifest.reserve(batch.batch_id, placed)
    try:
        for row in placed:
            stripes = stripe_words(row.values, archive.bits)
            for slot, word in zip(slot_addresses(row.address), stripes, strict=True):
                archive.notify('before_slot', row.address, INITIAL_REVISION, slot.role)
                write_slot(archive, slot, INITIAL_REVISION, word)
                archive.notify('after_slot', row.address, INITIAL_REVISION, slot.role)
    except SlotUnavailable as exc:
        raise SealIncomplete(f'batch {batch.batch_id} has uncommitted blocks') from exc
    published = manifest.publish(batch.batch_id)
    return SealReceipt(published.batch_id, published.members)
