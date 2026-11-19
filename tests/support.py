import os
import sqlite3
import subprocess
import sys
from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from lake.amend.apply import apply_correction
from lake.amend.requests import CorrectionRequest
from lake.archive import Archive
from lake.batch.intake import make_batch_input
from lake.batch.seal import seal_batch
from lake.volume.layout import SlotRole


EXIT_CODES = {'before_slot': 71, 'after_slot': 72, 'after_publish': 73}


@contextmanager
def fresh(*, bits=8):
    with TemporaryDirectory(prefix='luwan-test-') as directory:
        yield Archive.initialize(directory, bits=bits)


def seal_pair(archive, first=5, second=9):
    receipt = seal_batch(archive, make_batch_input('L01', [('R03', first, second)]))
    return receipt.members[0].address


@contextmanager
def offlined(archive, *roles):
    moved = []
    try:
        for role in roles:
            live = archive.volume(role).path
            offline = live.with_suffix('.offline')
            live.rename(offline)
            moved.append((offline, live))
        yield
    finally:
        for offline, live in reversed(moved):
            offline.rename(live)


def remove_block(archive, address, role):
    volume_path = archive.volume(role).path
    with closing(sqlite3.connect(volume_path)) as db, db:
        deleted = db.execute('DELETE FROM blocks WHERE batch_id = ? AND ordinal = ?',
                             (address.batch_id, address.ordinal))
        if deleted.rowcount != 1:
            raise AssertionError(f'fixture block did not exist at {address}, {role}')


def terminate_at(archive, phase):
    return subprocess.run(
        [sys.executable, '-B', '-m', 'tests.support', str(archive.root), phase],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=20,
    )


def _run_correction(path, phase):
    def stop(event):
        if event.phase != phase or event.revision != 2:
            return
        if phase == 'after_publish' or event.role is SlotRole.FIRST:
            os._exit(EXIT_CODES[phase])

    archive = Archive.open(path, on_event=stop)
    address = archive.manifest.lookup_batch('L01').members[0].address
    apply_correction(archive, CorrectionRequest('C01', address, SlotRole.FIRST, 6))
    raise AssertionError(f'termination boundary was not reached: {phase}')


if __name__ == '__main__':
    _, directory, boundary = sys.argv
    _run_correction(directory, boundary)
