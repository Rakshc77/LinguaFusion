"""Read-only deployment preflight. Creates nothing, enables nothing."""
import json

import google.auth
from google.auth.transport.requests import AuthorizedSession

PROJECT = 'linguafusion-f24fe'
REGION = 'europe-west3'
RUNTIME_SA = f'linguafusion-be@{PROJECT}.iam.gserviceaccount.com'
SERVICES = ['run.googleapis.com', 'firestore.googleapis.com', 'cloudbuild.googleapis.com',
            'artifactregistry.googleapis.com', 'secretmanager.googleapis.com',
            'vision.googleapis.com', 'identitytoolkit.googleapis.com',
            'cloudresourcemanager.googleapis.com', 'iam.googleapis.com']


def main():
    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    credentials = credentials.with_quota_project(PROJECT)
    with AuthorizedSession(credentials) as session:
        billing = session.get(
            f'https://cloudbilling.googleapis.com/v1/projects/{PROJECT}/billingInfo', timeout=20)
        if billing.status_code == 200:
            data = billing.json()
            print(json.dumps({'stage': 'billing', 'enabled': data.get('billingEnabled'),
                              'account_linked': bool(data.get('billingAccountName'))}))
        else:
            print(json.dumps({'stage': 'billing', 'http_status': billing.status_code}))

        states = {}
        for service in SERVICES:
            response = session.get(
                f'https://serviceusage.googleapis.com/v1/projects/{PROJECT}/services/{service}', timeout=20)
            states[service] = response.json().get('state', 'unknown') if response.status_code == 200 else f'HTTP {response.status_code}'
        print(json.dumps({'stage': 'services', **states}, indent=1))

        response = session.get(
            f'https://firestore.googleapis.com/v1/projects/{PROJECT}/databases', timeout=20)
        print(json.dumps({'stage': 'databases', 'http_status': response.status_code,
                          'count': len(response.json().get('databases', [])) if response.status_code == 200 else None}))

        # Does the runtime service account exist at all?
        response = session.get(
            f'https://iam.googleapis.com/v1/projects/{PROJECT}/serviceAccounts/{RUNTIME_SA}', timeout=20)
        print(json.dumps({'stage': 'runtime_service_account', 'http_status': response.status_code,
                          'exists': response.status_code == 200,
                          'disabled': response.json().get('disabled') if response.status_code == 200 else None}))

        response = session.post(
            f'https://cloudresourcemanager.googleapis.com/v1/projects/{PROJECT}:getIamPolicy',
            json={}, timeout=20)
        if response.status_code == 200:
            member = 'serviceAccount:' + RUNTIME_SA
            print(json.dumps({'stage': 'runtime_roles',
                              'roles': [b.get('role') for b in response.json().get('bindings', [])
                                        if member in b.get('members', []) and not b.get('condition')]}))

        # Any Cloud Run service already deployed in the target region?
        response = session.get(
            f'https://{REGION}-run.googleapis.com/apis/serving.knative.dev/v1/namespaces/{PROJECT}/services',
            timeout=20)
        print(json.dumps({'stage': 'existing_cloud_run', 'region': REGION,
                          'http_status': response.status_code,
                          'services': [i['metadata']['name'] for i in response.json().get('items', [])]
                          if response.status_code == 200 else None}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'stage': 'failed', 'error_type': type(error).__name__}))
        raise SystemExit(1)
