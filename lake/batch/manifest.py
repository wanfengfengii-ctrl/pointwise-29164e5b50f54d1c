import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from lake.batch.placement import PlacedRow
from lake.volume.layout import StripeAddress, make_stripe_address


class BatchAlreadyExists(ValueError):
    pass


class BatchNotReserved(RuntimeError):
    pass


@dataclass(frozen=True)
class BatchMember:
    address: StripeAddress
    row_id: str


@dataclass(frozen=True)
class BatchManifest:
    batch_id: str
    members: tuple[BatchMember, ...]


def catalog_connection(path, mode='rw'):
    db = sqlite3.connect(f'{Path(path).absolute().as_uri()}?mode={mode}', uri=True)
    db.execute('PRAGMA foreign_keys = ON')
    return db


class ManifestStore:
    def __init__(self, path):
        self.path = Path(path)

    def initialize(self, bits):
        with closing(catalog_connection(self.path, 'rwc')) as db, db:
            db.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE configuration (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    word_bits TEXT NOT NULL
                );
                CREATE TABLE batches (
                    batch_id TEXT PRIMARY KEY,
                    sealed INTEGER NOT NULL DEFAULT 0 CHECK (sealed IN (0, 1))
                );
                CREATE TABLE members (
                    batch_id TEXT NOT NULL REFERENCES batches(batch_id),
                    ordinal INTEGER NOT NULL,
                    row_id TEXT NOT NULL,
                    PRIMARY KEY (batch_id, ordinal),
                    UNIQUE (batch_id, row_id)
                );
            ''')
            db.execute('INSERT INTO configuration VALUES (1, ?)', (str(bits),))

    def word_bits(self):
        with closing(catalog_connection(self.path, 'ro')) as db:
            row = db.execute('SELECT word_bits FROM configuration WHERE singleton = 1').fetchone()
            if row is None:
                raise RuntimeError('archive configuration is missing')
            return int(row[0])

    def reserve(self, batch_id, rows: tuple[PlacedRow, ...]):
        if not rows or any(row.address != make_stripe_address(batch_id, ordinal)
                           for ordinal, row in enumerate(rows)):
            raise ValueError('batch placement must be dense and ordered')
        with closing(catalog_connection(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            inserted = db.execute('INSERT INTO batches (batch_id) VALUES (?) ON CONFLICT DO NOTHING',
                                  (batch_id,))
            if inserted.rowcount != 1:
                raise BatchAlreadyExists(batch_id)
            db.executemany('INSERT INTO members VALUES (?, ?, ?)',
                           ((batch_id, row.address.ordinal, row.row_id) for row in rows))

    def publish(self, batch_id):
        with closing(catalog_connection(self.path)) as db, db:
            updated = db.execute('UPDATE batches SET sealed = 1 WHERE batch_id = ? AND sealed = 0',
                                 (batch_id,))
            if updated.rowcount != 1:
                raise BatchNotReserved(batch_id)
            return self._lookup_batch(db, batch_id)

    @staticmethod
    def _lookup_batch(db, batch_id):
        rows = db.execute('''
            SELECT m.ordinal, m.row_id FROM batches b JOIN members m USING (batch_id)
            WHERE b.batch_id = ? AND b.sealed = 1 ORDER BY m.ordinal
        ''', (batch_id,)).fetchall()
        if not rows:
            return None
        return BatchManifest(batch_id, tuple(
            BatchMember(make_stripe_address(batch_id, ordinal), row_id) for ordinal, row_id in rows
        ))

    def lookup_batch(self, batch_id):
        with closing(catalog_connection(self.path, 'ro')) as db:
            return self._lookup_batch(db, batch_id)

    def lookup_stripe(self, address):
        if not isinstance(address, StripeAddress):
            return None
        with closing(catalog_connection(self.path, 'ro')) as db:
            match = db.execute('''
                SELECT m.row_id FROM batches b JOIN members m USING (batch_id)
                WHERE b.sealed = 1 AND m.batch_id = ? AND m.ordinal = ?
            ''', (address.batch_id, address.ordinal)).fetchone()
        return None if match is None else BatchMember(address, match[0])
