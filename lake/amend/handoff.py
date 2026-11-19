from lake.amend.journal import AmendmentJournal, RequestRecord
from lake.volume.codec import decode_word
from lake.volume.layout import SlotRole
from lake.volume.parity import stripe_words


class OverwriteUnavailable(RuntimeError):
    pass


def plan_overwrite(journal: AmendmentJournal, record: RequestRecord, bits, read_base):
    with journal.pending_write(record) as db:
        if db is None:
            return None
        revision, (first, second) = read_base()
        if revision != record.base_revision:
            raise OverwriteUnavailable('base read did not use the requested revision')
        target = decode_word(record.word, bits)
        pair = (target, second) if record.role is SlotRole.FIRST else (first, target)
        return stripe_words(pair, bits)
