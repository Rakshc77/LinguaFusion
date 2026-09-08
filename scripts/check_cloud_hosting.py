"""Read-only hosting preflight. Never prints credentials or raw API errors."""
import google.auth
from google.auth.transport.requests import AuthorizedSession

PROJECT = 'linguafusion-f24fe'


def main():
    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    with AuthorizedSession(credentials) as session:
        for service in ['run.googleapis.com', 'firestore.googleapis.com',
                        'cloudbuild.googleapis.com', 'artifactregistry.googleapis.com',
                        'secretmanager.googleapis.com', 'vision.googleapis.com']:
            response = session.get(f'https://serviceusage.googleapis.com/v1/projects/{PROJECT}/services/{service}', timeout=15)
            print(service, response.json().get('state', 'unknown') if response.status_code == 200 else f'HTTP {response.status_code}')
        response = session.get(f'https://firestore.googleapis.com/v1/projects/{PROJECT}/databases', timeout=15)
        if response.status_code == 200:
            for database in response.json().get('databases', []):
                print('Database:', database.get('name', '').rsplit('/', 1)[-1],
                      'location:', database.get('locationId'), 'type:', database.get('type'))
            if not response.json().get('databases'):
                print('No Firestore databases found.')
        else:
            print('Database inventory HTTP', response.status_code)
        response = session.post(f'https://cloudresourcemanager.googleapis.com/v1/projects/{PROJECT}:getIamPolicy', json={}, timeout=15)
        if response.status_code == 200:
            account = f'serviceAccount:linguafusion-be@{PROJECT}.iam.gserviceaccount.com'
            print('Runtime account unconditional roles:',
                  [binding.get('role') for binding in response.json().get('bindings', [])
                   if account in binding.get('members', []) and not binding.get('condition')])
        else:
            print('Runtime role inventory HTTP', response.status_code)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Hosting preflight unavailable:', type(error).__name__)
        raise SystemExit(1)
