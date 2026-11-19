from dataclasses import dataclass


@dataclass(frozen=True)
class ObservationRow:
    row_id: str
    first: int
    second: int


@dataclass(frozen=True)
class BatchInput:
    batch_id: str
    rows: tuple[ObservationRow, ...]


def make_batch_input(batch_id, rows):
    return BatchInput(batch_id, tuple(
        row if isinstance(row, ObservationRow) else ObservationRow(*row)
        for row in rows
    ))
