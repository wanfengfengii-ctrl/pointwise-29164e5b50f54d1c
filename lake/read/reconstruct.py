from lake.read.blocks import RevisionWords
from lake.volume.parity import recover_word, stripe_parity


class InsufficientWords(RuntimeError):
    pass


def reconstruct_pair(words: RevisionWords, bits):
    first, second, parity = words.first, words.second, words.parity
    if sum(word is None for word in (first, second, parity)) > 1:
        raise InsufficientWords('fewer than two same-revision words')
    if first is None:
        return recover_word(second, parity, bits), second
    if second is None:
        return first, recover_word(first, parity, bits)
    if parity is not None and stripe_parity(first, second, bits) != parity:
        raise InsufficientWords('same-revision words fail XOR verification')
    return first, second
