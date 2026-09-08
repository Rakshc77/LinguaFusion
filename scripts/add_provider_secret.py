"""Put a provider API key into Secret Manager, straight from a local file.

The key material goes from your disk to Google Secret Manager and nowhere else.
This script never prints the key, never logs it, and never copies it into the
repository. Run it yourself; nobody else needs to see the value.

  python scripts/add_provider_secret.py --provider openrouter --file C:\\path\\keys.txt
  python scripts/add_provider_secret.py --provider groq       --file C:\\path\\keys.txt

If the file holds more than one key, the script tells you how many lines it
found (never their contents) and you pick one with --line N.

Afterwards, delete the text file. A secret in a .txt on disk is the weakest
link in this whole setup.
"""
import argparse
import json
import pathlib
import sys
import warnings

warnings.filterwarnings('ignore', category=FutureWarning)

import google.auth  # noqa: E402
from google.auth.transport.requests import AuthorizedSession  # noqa: E402

PROJECT = 'linguafusion-f24fe'
REGION = 'europe-west3'
RUNTIME_SA = f'linguafusion-be@{PROJECT}.iam.gserviceaccount.com'

PROVIDERS = {
    'openrouter': {'secret': 'lf-openrouter-key', 'prefix': 'sk-or-'},
    'groq': {'secret': 'lf-groq-key', 'prefix': 'gsk_'},
}


def read_key(path, line_number):
    text = pathlib.Path(path).read_text(encoding='utf-8-sig')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise SystemExit('That file is empty.')
    if line_number is None:
        if len(lines) > 1:
            raise SystemExit(
                f'That file has {len(lines)} non-empty lines. Re-run with --line N '
                f'to choose one (1-{len(lines)}). Contents are never displayed.')
        line_number = 1
    if not 1 <= line_number <= len(lines):
        raise SystemExit(f'--line must be between 1 and {len(lines)}.')
    key = lines[line_number - 1]
    # A key line may be written as "openrouter: sk-or-..." — take the last field.
    if ' ' in key or '\t' in key:
        key = key.split()[-1]
    if key.endswith(','):
        key = key[:-1]
    return key.strip().strip('"').strip("'")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', required=True, choices=sorted(PROVIDERS))
    parser.add_argument('--file', required=True)
    parser.add_argument('--line', type=int, default=None)
    parser.add_argument('--add-version', action='store_true',
                        help='add a new version even though one exists (key rotation)')
    parser.add_argument('--force', action='store_true',
                        help='skip the expected-prefix check if a provider changes its format')
    arguments = parser.parse_args()

    spec = PROVIDERS[arguments.provider]
    key = read_key(arguments.file, arguments.line)

    # Validate without ever revealing the value.
    if any(character.isspace() for character in key):
        raise SystemExit('That value contains whitespace; the backend would reject it.')
    if not 20 <= len(key) <= 400:
        raise SystemExit(f'That value is {len(key)} characters, which does not look like an API key.')
    if not key.startswith(spec['prefix']) and not arguments.force:
        raise SystemExit(
            f"That value does not start with '{spec['prefix']}', which {arguments.provider} keys do. "
            f'Check you picked the right line, or pass --force if the format has changed.')
    print(json.dumps({'stage': 'read', 'provider': arguments.provider,
                      'length': len(key), 'prefix_ok': True}))

    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    credentials = credentials.with_quota_project(PROJECT)
    import base64
    with AuthorizedSession(credentials) as session:
        base = f'https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets'
        name = spec['secret']

        if session.get(f'{base}/{name}', timeout=30).status_code != 200:
            created = session.post(base, params={'secretId': name}, timeout=60, json={
                'replication': {'userManaged': {'replicas': [{'location': REGION}]}}})
            print(json.dumps({'stage': 'create_secret', 'http_status': created.status_code}))
            if created.status_code not in (200, 201):
                return 1
        else:
            print(json.dumps({'stage': 'create_secret', 'skipped': 'already exists'}))

        listing = session.get(f'{base}/{name}/versions', timeout=30)
        live = [v for v in listing.json().get('versions', []) if v.get('state') == 'ENABLED']             if listing.status_code == 200 else []
        if live and not arguments.add_version:
            print(json.dumps({'stage': 'add_version', 'skipped': f'{len(live)} enabled version(s) already exist',
                              'note': 'pass --add-version to rotate the key'}))
            added = None
        else:
            added = session.post(f'{base}/{name}:addVersion', timeout=60, json={
                'payload': {'data': base64.b64encode(key.encode()).decode()}})
        if added is not None:
            print(json.dumps({'stage': 'add_version', 'http_status': added.status_code}))
            if added.status_code not in (200, 201):
                return 1
            version = added.json().get('name', '').rsplit('/', 1)[-1]
        else:
            version = live[0].get('name', '').rsplit('/', 1)[-1]

        # Grant the runtime account access to THIS secret only, never project-wide.
        policy = session.get(f'{base}/{name}:getIamPolicy', timeout=30).json()
        member = f'serviceAccount:{RUNTIME_SA}'
        binding = next((b for b in policy.setdefault('bindings', [])
                        if b.get('role') == 'roles/secretmanager.secretAccessor'), None)
        if binding is None:
            policy['bindings'].append({'role': 'roles/secretmanager.secretAccessor', 'members': [member]})
        elif member not in binding.setdefault('members', []):
            binding['members'].append(member)
        else:
            policy = None
        if policy is not None:
            granted = session.post(f'{base}/{name}:setIamPolicy', json={'policy': policy}, timeout=60)
            print(json.dumps({'stage': 'grant_accessor', 'http_status': granted.status_code}))

        print(json.dumps({'stage': 'done', 'secret': name, 'version': version,
                          'reminder': 'delete the text file now'}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
