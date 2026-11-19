from lake.batch.intake import BatchInput, ObservationRow
from lake.volume.codec import InvalidWord, validate_word
from lake.volume.layout import valid_identifier


class InvalidBatch(ValueError):
    pass


def validate_intake(batch, bits):
    if not isinstance(batch, BatchInput) or not valid_identifier(batch.batch_id):
        raise InvalidBatch('invalid batch identifier')
    if not isinstance(batch.rows, tuple) or not batch.rows:
        raise InvalidBatch('batch requires a nonempty ordered tuple of rows')
    seen = set()
    for row in batch.rows:
        if not isinstance(row, ObservationRow) or not valid_identifier(row.row_id):
            raise InvalidBatch('invalid observation row identifier')
        if row.row_id in seen:
            raise InvalidBatch(f'duplicate observation row {row.row_id}')
        seen.add(row.row_id)
        try:
            validate_word(row.first, bits)
            validate_word(row.second, bits)
        except InvalidWord as exc:
            raise InvalidBatch(f'invalid observation for {row.row_id}: {exc}') from exc
