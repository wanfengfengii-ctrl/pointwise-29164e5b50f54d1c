from dataclasses import dataclass

from lake.volume.codec import InvalidWord, encode_word, validate_word
from lake.volume.layout import SlotRole, StripeAddress, valid_identifier


class InvalidCorrection(ValueError):
    pass


@dataclass(frozen=True)
class CorrectionRequest:
    request_id: str
    address: StripeAddress
    role: SlotRole
    new_value: int


def normalize_request(request, bits):
    if not isinstance(request, CorrectionRequest) or not valid_identifier(request.request_id):
        raise InvalidCorrection('invalid correction request identifier')
    if not isinstance(request.address, StripeAddress):
        raise InvalidCorrection('correction requires a fixed stripe address')
    try:
        role = SlotRole(request.role)
        validate_word(request.new_value, bits)
    except (ValueError, TypeError, InvalidWord) as exc:
        raise InvalidCorrection('invalid correction role or word') from exc
    if role is SlotRole.PARITY:
        raise InvalidCorrection('correction must target an observation')
    return CorrectionRequest(request.request_id, request.address, role, request.new_value)


def request_binding(request, bits):
    return (request.address.batch_id, request.address.ordinal, request.role.value,
            encode_word(request.new_value, bits))
