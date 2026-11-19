from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from lake.amend.journal import AmendmentJournal
from lake.batch.manifest import ManifestStore
from lake.volume.codec import validate_bits
from lake.volume.layout import SlotRole, StripeAddress
from lake.volume.store import VolumeStore


class ArchiveConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ArchiveEvent:
    phase: str
    address: StripeAddress
    revision: int
    role: SlotRole | None = None


@dataclass(frozen=True)
class Archive:
    root: Path
    bits: int
    on_event: Callable[[ArchiveEvent], None] | None = None

    @classmethod
    def initialize(cls, path, bits=None, *, on_event=None):
        if bits is not None:
            validate_bits(bits)
        root = Path(path).absolute()
        root.mkdir(parents=True, exist_ok=True)
        if (root / 'catalog.sqlite3').is_file():
            archive = cls.open(root, on_event=on_event)
            if bits is not None and archive.bits != bits:
                raise ArchiveConfigurationError('configured word width differs')
            return archive
        if any(root.iterdir()):
            raise ArchiveConfigurationError('new archive requires an empty directory')
        archive = cls(root, 8 if bits is None else bits, on_event)
        for role in SlotRole:
            archive.volume(role).initialize()
        archive.journal.initialize()
        archive.manifest.initialize(archive.bits)
        return archive

    @classmethod
    def open(cls, path, *, on_event=None):
        root = Path(path).absolute()
        catalog = root / 'catalog.sqlite3'
        if not catalog.is_file():
            raise ArchiveConfigurationError('archive directory is not initialized')
        bits = ManifestStore(catalog).word_bits()
        validate_bits(bits)
        return cls(root, bits, on_event)

    @property
    def manifest(self):
        return ManifestStore(self.root / 'catalog.sqlite3')

    @property
    def journal(self):
        return AmendmentJournal(self.root / 'catalog.sqlite3')

    def volume(self, role):
        return VolumeStore(self.root / f'{SlotRole(role).value}.sqlite3')

    def notify(self, phase, address, revision, role=None):
        if self.on_event is not None:
            self.on_event(ArchiveEvent(phase, address, revision, role))
