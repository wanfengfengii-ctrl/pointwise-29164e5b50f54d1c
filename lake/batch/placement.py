from dataclasses import dataclass

from lake.batch.intake import BatchInput
from lake.volume.layout import StripeAddress, make_stripe_address


@dataclass(frozen=True)
class PlacedRow:
    address: StripeAddress
    row_id: str
    values: tuple[int, int]


def place_rows(batch: BatchInput):
    return tuple(
        PlacedRow(make_stripe_address(batch.batch_id, ordinal), row.row_id, (row.first, row.second))
        for ordinal, row in enumerate(batch.rows)
    )
