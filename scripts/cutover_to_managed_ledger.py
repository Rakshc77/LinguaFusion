"""Readiness gate 5: move the lifetime allowance into the managed cloud ledger.

Run once, deliberately, with --confirm.

Ordering is the whole safety argument. The local ledger is CLOSED FIRST, then
the cloud ledger is created:

  close local -> create cloud   If creating the cloud ledger fails, nothing can
                                spend anywhere. Recoverable, and this script
                                rolls the local mark back only after proving the
                                cloud document does not exist.

  create cloud -> close local   If closing fails, the local file AND the cloud
                                document each permit the remaining allowance.
                                That is the exact hazard gate 5 forbids, so this
                                order is never used.

The cloud document is written with create-only semantics. It is never set or
overwritten, because overwriting would re-seed a fresh US$5 allowance.
"""
import argparse
import json
import sys
import warnings

warnings.filterwarnings('ignore', category=FutureWarning)

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))

from cloud_api.firestore_policy import new_state  # noqa: E402
from cloud_api.test_budget import TestBudget  # noqa: E402

PROJECT = 'linguafusion-f24fe'
DATABASE = '(default)'
OWNER_UID = 'kLqjJka0cHXTCZX0TQxA2QMlzKi1'
LEDGER_PATH = 'cloud_api/local-data/combined-test-budget.sqlite3'
COLLECTION = 'linguafusion_private'
DOCUMENT = 'pilot_policy_v1'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--confirm', action='store_true',
                        help='actually perform the cutover; without it this only reports')
    parser.add_argument('--ledger', default=LEDGER_PATH)
    arguments = parser.parse_args()

    from google.cloud import firestore

    budget = TestBudget(arguments.ledger)
    carried = budget.carry_forward_micro()
    already = budget.cutover_at()
    summary = budget.summary()
    print(json.dumps({'stage': 'local_ledger', 'path': arguments.ledger,
                      'carry_forward_micro': carried,
                      'carry_forward_usd': f'{carried / 1_000_000:.6f}',
                      'unreconciled_requests': summary['unreconciled_requests'],
                      'already_cutover': already}, indent=1))

    client = firestore.Client(project=PROJECT, database=DATABASE)
    document = client.collection(COLLECTION).document(DOCUMENT)
    exists = document.get(timeout=20).exists
    print(json.dumps({'stage': 'cloud_ledger', 'exists': exists}))

    if exists:
        print(json.dumps({'stage': 'abort',
                          'reason': 'the managed ledger already exists; never overwrite it'}))
        return 1
    if already:
        print(json.dumps({'stage': 'abort',
                          'reason': 'local ledger is already closed but no cloud ledger exists',
                          'action': 'investigate before proceeding; do not clear the mark blindly'}))
        return 1
    if not arguments.confirm:
        print(json.dumps({'stage': 'dry_run', 'would_create_prior_reserved': carried,
                          'note': 're-run with --confirm to perform the cutover'}))
        return 0

    # Validate the payload BEFORE closing anything, so a bad value cannot leave
    # the local ledger shut with no cloud ledger to replace it.
    state = new_state(OWNER_UID, carried)

    stamp = budget.mark_cutover(f'carried {carried} micro-USD to {COLLECTION}/{DOCUMENT}')
    print(json.dumps({'stage': 'local_closed', 'at': stamp}))
    try:
        document.create(state)          # create-only: fails if it already exists
        print(json.dumps({'stage': 'cloud_created', 'prior_reserved': carried}))
    except Exception as error:
        # Roll back only if we can prove nothing was created.
        if not document.get(timeout=20).exists:
            budget.clear_cutover()
            print(json.dumps({'stage': 'rolled_back', 'error_type': type(error).__name__,
                              'note': 'cloud ledger absent, local spending reopened'}))
        else:
            print(json.dumps({'stage': 'manual_review', 'error_type': type(error).__name__,
                              'note': 'cloud document exists; local stays closed'}))
        return 1

    stored = document.get(timeout=20).to_dict()
    try:
        budget.reserve('openrouter', 1)
        local_refuses = False
    except ValueError:
        local_refuses = True
    print(json.dumps({'stage': 'verify',
                      'cloud_prior_reserved': stored.get('prior_reserved'),
                      'cloud_ceiling': stored.get('ceiling'),
                      'cloud_remaining_usd': f"{(stored.get('ceiling', 0) - stored.get('prior_reserved', 0)) / 1_000_000:.6f}",
                      'local_refuses_new_spending': local_refuses,
                      'owner_enabled': bool(stored.get('users'))}, indent=1))
    return 0 if local_refuses and stored.get('prior_reserved') == carried else 1


if __name__ == '__main__':
    sys.exit(main())
