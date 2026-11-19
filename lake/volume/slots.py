import sqlite3
from dataclasses import dataclass

from lake.archive import Archive
from lake.volume.codec import InvalidWord, decode_word, encode_word
from lake.volume.layout import SlotAddress
from lake.volume.store import VolumeConflict


class SlotUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SlotBlock:
    address: SlotAddress
    revision: int
    value: int


def read_slot(archive: Archive, address: SlotAddress, revision=None):
    try:
        record = archive.volume(address.role).read_record(address.stripe, revision)
        if record is None:
            raise SlotUnavailable(f'block missing at {address}')
        block_revision, data = record
        return SlotBlock(address, block_revision, decode_word(data, archive.bits))
    except (sqlite3.Error, InvalidWord) as exc:
        raise SlotUnavailable(f'cannot read {address}') from exc


def write_slot(archive: Archive, address: SlotAddress, revision, value):
    encoded = encode_word(value, archive.bits)
    try:
        return archive.volume(address.role).write_record(address.stripe, revision, encoded)
    except (sqlite3.Error, VolumeConflict) as exc:
        raise SlotUnavailable(f'cannot commit {address} at revision {revision}') from exc
