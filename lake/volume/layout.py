import re
from dataclasses import dataclass
from enum import Enum


_IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}')
INITIAL_REVISION = 1


def valid_identifier(value):
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


class SlotRole(str, Enum):
    FIRST = 'first'
    SECOND = 'second'
    PARITY = 'parity'


@dataclass(frozen=True)
class StripeAddress:
    batch_id: str
    ordinal: int

    def __post_init__(self):
        if not valid_identifier(self.batch_id):
            raise ValueError('invalid address batch identifier')
        if type(self.ordinal) is not int or not 0 <= self.ordinal < 2**63:
            raise ValueError('stripe ordinal must be a nonnegative SQLite integer')


@dataclass(frozen=True)
class SlotAddress:
    stripe: StripeAddress
    role: SlotRole


def make_stripe_address(batch_id, ordinal):
    return StripeAddress(batch_id, ordinal)


def slot_addresses(address):
    return tuple(SlotAddress(address, role) for role in SlotRole)
