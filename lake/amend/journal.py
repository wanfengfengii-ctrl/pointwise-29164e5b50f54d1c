from contextlib import closing, contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from lake.amend.requests import CorrectionRequest, request_binding
from lake.batch.manifest import catalog_connection
from lake.volume.layout import INITIAL_REVISION, SlotRole, StripeAddress


class RequestConflict(ValueError):
    pass


@dataclass(frozen=True)
class RequestRecord:
    request_id: str
    address: StripeAddress
    role: SlotRole
    word: bytes
    base_revision: int
    target_revision: int
    committed: bool

    @property
    def binding(self):
        return self.address.batch_id, self.address.ordinal, self.role.value, self.word


@dataclass(frozen=True)
class RevisionRecord:
    address: StripeAddress
    revision: int


def _key(address):
    return address.batch_id, address.ordinal


class AmendmentJournal:
    def __init__(self, path):
        self.path = Path(path)

    def initialize(self):
        with closing(catalog_connection(self.path, 'rwc')) as db, db:
            db.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE revisions (
                    batch_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    PRIMARY KEY (batch_id, ordinal)
                );
                CREATE TABLE requests (
                    request_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('first', 'second')),
                    word BLOB NOT NULL,
                    base_revision INTEGER NOT NULL,
                    target_revision INTEGER NOT NULL CHECK (target_revision = base_revision + 1),
                    committed INTEGER NOT NULL DEFAULT 0 CHECK (committed IN (0, 1))
                );
                CREATE UNIQUE INDEX one_pending_request
                    ON requests (batch_id, ordinal) WHERE committed = 0;
                COMMIT;
            ''')

    @contextmanager
    def _write(self):
        with closing(catalog_connection(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            yield db

    @staticmethod
    def _get_request(db, request_id):
        row = db.execute('''
            SELECT request_id, batch_id, ordinal, role, word, base_revision, target_revision, committed
            FROM requests WHERE request_id = ?
        ''', (request_id,)).fetchone()
        if row is None:
            return None
        key, batch_id, ordinal, role, word, base, target, committed = row
        return RequestRecord(key, StripeAddress(batch_id, ordinal), SlotRole(role), word,
                             base, target, bool(committed))

    def get_request(self, request_id):
        with closing(catalog_connection(self.path, 'ro')) as db:
            return self._get_request(db, request_id)

    def register(self, request: CorrectionRequest, bits):
        binding = request_binding(request, bits)
        with self._write() as db:
            previous = self._get_request(db, request.request_id)
            if previous is not None:
                if previous.binding != binding:
                    raise RequestConflict(f'parameter conflict for {request.request_id}')
                return previous
            rival = db.execute('''
                SELECT request_id FROM requests WHERE batch_id = ? AND ordinal = ? AND committed = 0
            ''', _key(request.address)).fetchone()
            if rival is not None:
                raise RequestConflict(f'stripe has pending request {rival[0]}')
            base = self.read_revision_record(request.address, db=db).revision
            record = RequestRecord(request.request_id, request.address, request.role, binding[3],
                                   base, base + 1, False)
            db.execute('''
                INSERT INTO requests (request_id, batch_id, ordinal, role, word, base_revision, target_revision)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (record.request_id, *binding, record.base_revision, record.target_revision))
            return record

    @contextmanager
    def pending_write(self, record):
        # Hold the directory writer reservation until this independent slot write ends.
        with self._write() as db:
            current = self._get_request(db, record.request_id)
            if current is None or current.binding != record.binding:
                raise RequestConflict(f'request changed: {record.request_id}')
            yield None if current.committed else db

    def read_revision_record(self, address, *, db=None):
        if db is not None:
            return self._read_revision(db, address)
        with closing(catalog_connection(self.path, 'ro')) as connection:
            return self._read_revision(connection, address)

    @staticmethod
    def _read_revision(db, address):
        row = db.execute('SELECT revision FROM revisions WHERE batch_id = ? AND ordinal = ?',
                         _key(address)).fetchone()
        return RevisionRecord(address, INITIAL_REVISION if row is None else row[0])

    def commit_effective(self, record):
        with self._write() as db:
            current = self._get_request(db, record.request_id)
            if current is None or current.binding != record.binding:
                raise RequestConflict(f'no matching request {record.request_id}')
            if current.committed:
                return current, False
            revision = self.read_revision_record(current.address, db=db).revision
            if revision != current.base_revision:
                raise RequestConflict(f'stripe revision changed for {current.request_id}')
            db.execute('''
                INSERT INTO revisions VALUES (?, ?, ?)
                ON CONFLICT (batch_id, ordinal) DO UPDATE SET revision = excluded.revision
            ''', (*_key(current.address), current.target_revision))
            db.execute('UPDATE requests SET committed = 1 WHERE request_id = ?', (current.request_id,))
            return replace(current, committed=True), True
