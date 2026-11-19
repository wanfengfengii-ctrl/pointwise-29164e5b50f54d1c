class InvalidWord(ValueError):
    pass


def validate_bits(bits):
    if type(bits) is not int or bits <= 0:
        raise InvalidWord('word width must be a positive integer')
    return bits


def validate_word(value, bits):
    validate_bits(bits)
    if type(value) is not int or value < 0 or value.bit_length() > bits:
        raise InvalidWord(f'expected an unsigned {bits}-bit integer')
    return value


def word_size(bits):
    return (validate_bits(bits) + 7) // 8


def encode_word(value, bits):
    return validate_word(value, bits).to_bytes(word_size(bits), 'big')


def decode_word(data, bits):
    if not isinstance(data, bytes) or len(data) != word_size(bits):
        raise InvalidWord('incorrect encoded word length')
    return validate_word(int.from_bytes(data, 'big'), bits)
