"""Read-only Google setup diagnostics; no OCR and no tokens in output."""
import google.auth
from google.auth.transport.requests import AuthorizedSession

def main():
    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    with AuthorizedSession(credentials) as session:
        checks = [
            ('billing', 'https://cloudbilling.googleapis.com/v1/projects/linguafusion-f24fe/billingInfo', 'billingEnabled'),
            ('vision_api', 'https://serviceusage.googleapis.com/v1/projects/linguafusion-f24fe/services/vision.googleapis.com', 'state'),
        ]
        for label, url, field in checks:
            response = session.get(url, timeout=20)
            if response.status_code == 200:
                print(label, field, response.json().get(field, 'unknown'))
            else:
                print(label, 'HTTP', response.status_code)
                try:
                    reasons = [d.get('reason') for d in response.json().get('error', {}).get('details', [])]
                    print('Known reasons:', [r for r in reasons if r in {'BILLING_DISABLED', 'SERVICE_DISABLED', 'USER_PROJECT_DENIED', 'IAM_PERMISSION_DENIED', 'ACCESS_TOKEN_SCOPE_INSUFFICIENT'}])
                except ValueError:
                    pass

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Diagnostic unavailable:', type(error).__name__)
