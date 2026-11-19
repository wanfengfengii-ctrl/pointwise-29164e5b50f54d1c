from collections.abc import Iterable

from lake.read.result import ReadResult


def sum_observations(rows: Iterable[ReadResult]):
    return sum(value for row in rows for value in row.values)
