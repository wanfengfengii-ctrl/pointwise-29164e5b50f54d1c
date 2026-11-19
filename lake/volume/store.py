import sqlite3
from contextlib import closing
from pathlib import Path

from lake.volume.layout import StripeAddress


class VolumeConflict(RuntimeError):
    pass


class VolumeStore:
    def __init__(self, path):
        self.path = Path(path).absolute()

    def initialize(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('''
                CREATE TABLE blocks (
                    batch_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 1),
                    word BLOB NOT NULL,
                    PRIMARY KEY (batch_id, ordinal, revision)
                )
            ''')

    def _connect(self, mode):
        return sqlite3.connect(f'{self.path.as_uri()}?mode={mode}', uri=True)

    def read_record(self, address: StripeAddress, revision=None):
        with closing(self._connect('ro')) as db:
            return self._read(db, address, revision)

    @staticmethod
    def _read(db, address, revision=None):
        # Each revision keeps its own immutable row: correcting a slot adds a
        # revision instead of overwriting the published one, so a pinned read
        # never mixes words from different revisions.
        if revision is not None:
            return db.execute('''
                SELECT revision, word FROM blocks
                WHERE batch_id = ? AND ordinal = ? AND revision = ?
            ''', (address.batch_id, address.ordinal, revision)).fetchone()
        return db.execute('''
            SELECT revision, word FROM blocks
            WHERE batch_id = ? AND ordinal = ? ORDER BY revision DESC LIMIT 1
        ''', (address.batch_id, address.ordinal)).fetchone()

    def write_record(self, address: StripeAddress, revision, word):
        with closing(self._connect('rw')) as db, db:
            db.execute('BEGIN IMMEDIATE')
            existing = self._read(db, address, revision)
            if existing == (revision, word):
                return False
            if existing is not None:
                raise VolumeConflict(f'conflicting block at {address} revision {revision}')
            latest = self._read(db, address)
            if latest is not None and latest[0] > revision:
                raise VolumeConflict(f'older block at {address} revision {revision}')
            db.execute('''
                INSERT INTO blocks (batch_id, ordinal, revision, word) VALUES (?, ?, ?, ?)
            ''', (address.batch_id, address.ordinal, revision, word))
        return True
