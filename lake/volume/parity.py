from lake.volume.codec import validate_word


def stripe_parity(first, second, bits):
    return validate_word(first, bits) ^ validate_word(second, bits)


def recover_word(surviving_observation, parity, bits):
    return validate_word(surviving_observation, bits) ^ validate_word(parity, bits)


def stripe_words(pair, bits):
    first, second = pair
    return first, second, stripe_parity(first, second, bits)
