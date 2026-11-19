from dataclasses import dataclass

from lake.batch.manifest import BatchMember
from lake.volume.layout import StripeAddress


class StripeUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ReadResult:
    address: StripeAddress
    row_id: str
    revision: int
    values: tuple[int, int]


def make_read_result(member: BatchMember, revision, values):
    first, second = values
    return ReadResult(member.address, member.row_id, revision, (first, second))
