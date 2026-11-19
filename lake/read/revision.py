from dataclasses import dataclass

from lake.amend.journal import RevisionRecord
from lake.archive import Archive
from lake.batch.manifest import BatchMember
from lake.read.result import StripeUnavailable


@dataclass(frozen=True)
class ReadRevision:
    member: BatchMember
    record: RevisionRecord

    @property
    def revision(self):
        return self.record.revision


def pin_revision(archive: Archive, address):
    member = archive.manifest.lookup_stripe(address)
    if member is None:
        raise StripeUnavailable(f'no sealed stripe at {address}')
    record = archive.journal.read_revision_record(address)
    return ReadRevision(member, record)


def revision_is_current(archive: Archive, pinned: ReadRevision):
    return pinned.record == archive.journal.read_revision_record(pinned.member.address)
