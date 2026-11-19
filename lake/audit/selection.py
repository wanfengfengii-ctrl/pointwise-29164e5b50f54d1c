from lake.archive import Archive
from lake.audit.reconcile import match_members
from lake.audit.result import AuditUnavailable, make_audit_result
from lake.audit.totals import sum_observations
from lake.read.collect import read_stripe
from lake.read.result import StripeUnavailable
from lake.volume.layout import valid_identifier


def audit_batch(archive: Archive, batch_id):
    if not valid_identifier(batch_id):
        raise AuditUnavailable('invalid batch identifier')
    manifest = archive.manifest.lookup_batch(batch_id)
    if manifest is None:
        raise AuditUnavailable(f'no sealed batch {batch_id}')
    try:
        rows = tuple(read_stripe(archive, member.address) for member in manifest.members)
    except StripeUnavailable as exc:
        raise AuditUnavailable(f'cannot issue complete ledger for {batch_id}') from exc
    match_members(manifest, rows)
    return make_audit_result(batch_id, rows, sum_observations(rows))
