"""Set the shared lifetime spending ceiling on the managed ledger.

The ceiling is the ONLY hard stop on AI spending. Per-user monthly budgets
renew every month; this does not. It is the number that decides the worst case.

  python scripts/set_spending_ceiling.py                 # report only
  python scripts/set_spending_ceiling.py --usd 27 --confirm

Lowering is allowed, but never below what has already been committed: charges
already recorded or still held cannot be un-spent.

Note the ledger counts USD while the billing account is EUR, so the euro figure
drifts with the exchange rate. Treat any euro equivalent as approximate.
"""
import argparse
import json
import sys
import warnings
from decimal import Decimal

warnings.filterwarnings('ignore', category=FutureWarning)

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))

from cloud_api.firestore_policy import FirestorePolicy  # noqa: E402

PROJECT = 'linguafusion-f24fe'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--usd', type=Decimal, help='new ceiling in USD, e.g. 27')
    parser.add_argument('--confirm', action='store_true')
    arguments = parser.parse_args()

    from google.cloud import firestore
    policy = FirestorePolicy(PROJECT, client=firestore.Client(project=PROJECT, database='(default)'))
    state = policy.document.get(timeout=20).to_dict()
    committed = state['prior_reserved'] + sum(
        c['reserved'] if c['actual'] is None else c['actual'] for c in state['charges'].values())
    print(json.dumps({
        'stage': 'current',
        'ceiling_usd': f"{state['ceiling'] / 1_000_000:.2f}",
        'committed_usd': f'{committed / 1_000_000:.2f}',
        'remaining_usd': f"{(state['ceiling'] - committed) / 1_000_000:.2f}",
        'users': len(state['users']),
    }, indent=1))

    if arguments.usd is None:
        print(json.dumps({'stage': 'report_only', 'note': 'pass --usd N --confirm to change it'}))
        return 0
    target = int(arguments.usd * 1_000_000)
    if target < committed:
        print(json.dumps({'stage': 'abort',
                          'reason': f'{arguments.usd} USD is below the {committed / 1_000_000:.2f} '
                                    'already committed; spent money cannot be un-spent'}))
        return 1
    if not 0 < target <= 1_000_000_000:
        print(json.dumps({'stage': 'abort', 'reason': 'ceiling out of range'}))
        return 1
    if not arguments.confirm:
        print(json.dumps({'stage': 'dry_run', 'would_set_usd': f'{target / 1_000_000:.2f}'}))
        return 0

    def operation(live):
        live['ceiling'] = target

    policy._mutate(operation)
    after = policy.document.get(timeout=20).to_dict()
    print(json.dumps({'stage': 'done', 'ceiling_usd': f"{after['ceiling'] / 1_000_000:.2f}",
                      'remaining_usd': f"{(after['ceiling'] - committed) / 1_000_000:.2f}"}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
