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
                    PRIMARY KEY (batch_id, ordinal)
                )
            ''')

    def _connect(self, mode):
        return sqlite3.connect(f'{self.path.as_uri()}?mode={mode}', uri=True)

    def read_record(self, address: StripeAddress):
        with closing(self._connect('ro')) as db:
            return self._read(db, address)

    @staticmethod
    def _read(db, address):
        return db.execute('''
            SELECT revision, word FROM blocks WHERE batch_id = ? AND ordinal = ?
        ''', (address.batch_id, address.ordinal)).fetchone()

    def write_record(self, address: StripeAddress, revision, word):
        with closing(self._connect('rw')) as db, db:
            db.execute('BEGIN IMMEDIATE')
            existing = self._read(db, address)
            if existing == (revision, word):
                return False
            if existing is not None and existing[0] >= revision:
                raise VolumeConflict(f'conflicting block at {address} revision {revision}')
            db.execute('''
                INSERT INTO blocks (batch_id, ordinal, revision, word) VALUES (?, ?, ?, ?)
                ON CONFLICT (batch_id, ordinal) DO UPDATE SET
                    revision = excluded.revision, word = excluded.word
            ''', (address.batch_id, address.ordinal, revision, word))
        return True
