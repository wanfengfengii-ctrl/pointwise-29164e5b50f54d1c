from lake.archive import Archive
from lake.read.blocks import choose_words
from lake.read.reconstruct import InsufficientWords, reconstruct_pair
from lake.read.result import StripeUnavailable, make_read_result
from lake.read.revision import pin_revision, revision_is_current
from lake.volume.layout import StripeAddress


def read_stripe(archive: Archive, address: StripeAddress, *, observe=True):
    while True:
        pinned = pin_revision(archive, address)
        if observe:
            archive.notify('after_pin', address, pinned.revision)
            observe = False
        words = choose_words(archive, pinned)
        try:
            pair = reconstruct_pair(words, archive.bits)
        except InsufficientWords as exc:
            if revision_is_current(archive, pinned):
                raise StripeUnavailable(f'cannot collect {address} at revision {pinned.revision}') from exc
            continue
        return make_read_result(pinned.member, pinned.revision, pair)
