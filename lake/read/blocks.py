from dataclasses import dataclass

from lake.archive import Archive
from lake.read.revision import ReadRevision
from lake.volume.layout import slot_addresses
from lake.volume.slots import SlotUnavailable, read_slot


@dataclass(frozen=True)
class RevisionWords:
    first: int | None
    second: int | None
    parity: int | None


def choose_words(archive: Archive, pinned: ReadRevision):
    words = [None, None, None]
    for index, slot in enumerate(slot_addresses(pinned.member.address)):
        try:
            block = read_slot(archive, slot, pinned.revision)
        except SlotUnavailable:
            continue
        if block.address == slot and block.revision == pinned.revision:
            words[index] = block.value
    return RevisionWords(*words)
