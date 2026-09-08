"""Email the owner when someone asks for cloud access.

Run this yourself with your own address; nothing here guesses it:

  python scripts/setup_request_alerts.py --email you@example.com

It creates a Cloud Monitoring email channel and an alert policy on the
linguafusion_access_requests log metric. Google sends a confirmation link to
that address the first time; the channel stays unverified until you click it.

The alert says only that a request arrived. Names, organisations and email
addresses never reach the logs, so open the owner console in the pilot page to
see who it was and decide.

Delivery is email only. SMS notification channels need a paid Monitoring tier
and bill separately from the AI allowance, so they are deliberately not used.
"""
import argparse
import json
import re
import sys
import warnings

warnings.filterwarnings('ignore', category=FutureWarning)

import google.auth  # noqa: E402
from google.auth.transport.requests import AuthorizedSession  # noqa: E402

PROJECT = 'linguafusion-f24fe'
METRIC = 'linguafusion_access_requests'
POLICY_NAME = 'LinguaFusion access request received'
LOG_FILTER = ('resource.type="cloud_run_revision" '
              'AND resource.labels.service_name="linguafusion-cloud-pilot" '
              'AND textPayload:"access_request_submitted"')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--email', required=True, help='where alerts should go')
    parser.add_argument('--recreate', action='store_true',
                        help='delete and rebuild the policy, e.g. to change its condition type')
    arguments = parser.parse_args()
    if not re.fullmatch(r'[^@\s]{1,64}@[^@\s]{3,190}\.[A-Za-z]{2,20}', arguments.email):
        raise SystemExit('That does not look like an email address.')

    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    credentials = credentials.with_quota_project(PROJECT)
    with AuthorizedSession(credentials) as session:
        base = f'https://monitoring.googleapis.com/v3/projects/{PROJECT}'

        existing = session.get(f'{base}/notificationChannels', timeout=30).json().get('notificationChannels', [])
        channel = next((c for c in existing
                        if c.get('type') == 'email' and c.get('labels', {}).get('email_address') == arguments.email), None)
        if channel is None:
            created = session.post(f'{base}/notificationChannels', timeout=60, json={
                'type': 'email', 'displayName': 'LinguaFusion owner',
                'labels': {'email_address': arguments.email}, 'enabled': True})
            print(json.dumps({'stage': 'channel', 'http_status': created.status_code}))
            if created.status_code not in (200, 201):
                print(created.text[:300])
                return 1
            channel = created.json()
        else:
            print(json.dumps({'stage': 'channel', 'reused': True}))
        print(json.dumps({'channel_verified': channel.get('verificationStatus')}))

        policies = session.get(f'{base}/alertPolicies', timeout=30).json().get('alertPolicies', [])
        current = next((p for p in policies if p.get('displayName') == POLICY_NAME), None)
        if current is not None and arguments.recreate:
            removed = session.delete(f"https://monitoring.googleapis.com/v3/{current['name']}", timeout=60)
            print(json.dumps({'stage': 'policy', 'deleted_http': removed.status_code}))
            current = None
        if current is not None:
            # Point the existing policy at this channel. Skipping here would
            # leave a corrected address created but never actually alerted to.
            if channel['name'] in current.get('notificationChannels', []):
                print(json.dumps({'stage': 'policy', 'already_attached': True}))
                return 0
            patched = session.patch(
                f"https://monitoring.googleapis.com/v3/{current['name']}",
                params={'updateMask': 'notificationChannels'},
                json={'notificationChannels': [channel['name']]}, timeout=60)
            print(json.dumps({'stage': 'policy', 'reattached_http': patched.status_code}))
            return 0 if patched.status_code == 200 else 1
        # A log-match condition fires directly on the log entry. The earlier
        # metric-threshold form depended on a thresholdValue of 0, which the API
        # drops as a proto default, leaving the condition ill-defined.
        policy = {
            'displayName': POLICY_NAME,
            'combiner': 'OR',
            'conditions': [{
                'displayName': 'An access request was submitted',
                'conditionMatchedLog': {'filter': LOG_FILTER},
            }],
            'notificationChannels': [channel['name']],
            'alertStrategy': {'notificationRateLimit': {'period': '300s'},
                              'autoClose': '1800s'},
            'documentation': {
                'content': 'Someone requested access to the LinguaFusion cloud pilot. '
                           'Open the pilot page, sign in as the owner, and review the '
                           'Access requests list. This alert carries no personal data.',
                'mimeType': 'text/markdown',
            },
        }
        created = session.post(f'{base}/alertPolicies', json=policy, timeout=60)
        print(json.dumps({'stage': 'policy', 'http_status': created.status_code}))
        if created.status_code not in (200, 201):
            print(created.text[:400])
            return 1
        print(json.dumps({'stage': 'done', 'policy': POLICY_NAME,
                          'note': 'confirm the email Google sends before relying on this'}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
