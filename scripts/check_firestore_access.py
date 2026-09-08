"""Read-only Firestore access diagnosis. Never prints credentials or raw errors.

Answers one question: why does listing databases return HTTP 403, and does a
database already exist? Readiness gate 1 forbids creating or relocating a
database before that is known.

Only allowlisted structured reason codes are printed, never the raw error text,
which can carry identifiers.
"""
import json

import google.auth
from google.auth.transport.requests import AuthorizedSession

PROJECT = 'linguafusion-f24fe'
# Reasons that explain a denial without revealing anything sensitive.
ALLOWED_REASONS = {'SERVICE_DISABLED', 'SERVICE_NOT_ACTIVATED', 'USER_PROJECT_DENIED',
                   'ACCESS_TOKEN_SCOPE_INSUFFICIENT', 'IAM_PERMISSION_DENIED',
                   'CONSUMER_INVALID', 'BILLING_DISABLED', 'CREDENTIALS_MISSING',
                   'API_KEY_SERVICE_BLOCKED', 'SERVICE_DISABLED_BY_ORG_POLICY'}


def reasons(response):
    try:
        error = response.json().get('error', {})
    except ValueError:
        return {}
    found = [detail['reason'] for detail in error.get('details', [])
             if isinstance(detail, dict) and detail.get('reason') in ALLOWED_REASONS]
    return {'status': error.get('status'), 'reasons': found}


def main():
    credentials, discovered = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    print(json.dumps({
        'stage': 'identity',
        'credential_type': type(credentials).__name__,
        'discovered_project': discovered,
        'quota_project': getattr(credentials, 'quota_project_id', None),
        'service_account': bool(getattr(credentials, 'service_account_email', None)),
    }))

    # User credentials need a quota project; a service account does not. Try both
    # so the failure is attributed correctly.
    for label, active in [('ambient', credentials),
                          ('explicit_quota_project', credentials.with_quota_project(PROJECT))]:
        with AuthorizedSession(active) as session:
            response = session.get(
                f'https://firestore.googleapis.com/v1/projects/{PROJECT}/databases', timeout=20)
            result = {'stage': 'databases_list', 'attempt': label, 'http_status': response.status_code}
            if response.status_code == 200:
                databases = response.json().get('databases', [])
                result['databases'] = [{'name': item.get('name', '').rsplit('/', 1)[-1],
                                        'location': item.get('locationId'),
                                        'type': item.get('type'),
                                        'delete_protection': item.get('deleteProtectionState')}
                                       for item in databases]
                result['database_count'] = len(databases)
            else:
                result.update(reasons(response))
            print(json.dumps(result))

    # Which Firestore permissions does this identity actually hold?
    with AuthorizedSession(credentials.with_quota_project(PROJECT)) as session:
        wanted = ['datastore.databases.list', 'datastore.databases.get',
                  'datastore.databases.create', 'serviceusage.services.enable',
                  'run.services.create', 'iam.serviceAccounts.actAs']
        response = session.post(
            f'https://cloudresourcemanager.googleapis.com/v1/projects/{PROJECT}:testIamPermissions',
            json={'permissions': wanted}, timeout=20)
        if response.status_code == 200:
            granted = set(response.json().get('permissions', []))
            print(json.dumps({'stage': 'permissions',
                              'granted': sorted(granted),
                              'missing': sorted(set(wanted) - granted)}))
        else:
            print(json.dumps({'stage': 'permissions', 'http_status': response.status_code,
                              **reasons(response)}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'stage': 'failed', 'error_type': type(error).__name__}))
        raise SystemExit(1)
