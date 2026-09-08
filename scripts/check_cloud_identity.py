"""Read-only pilot credential check. Never emits credentials or user records."""
import json
import warnings
import firebase_admin
from firebase_admin import auth, credentials
import google.auth

PROJECT = 'linguafusion-f24fe'
UID = 'kLqjJka0cHXTCZX0TQxA2QMlzKi1'

def main():
    warnings.filterwarnings('ignore', module='google.auth._default')
    try:
        credential, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    except Exception as error:
        print(json.dumps({'stage': 'credential_discovery', 'error_type': type(error).__name__}))
        return
    print(json.dumps({'stage': 'credential_discovery', 'available': True,
                      'quota_project_matches': getattr(credential, 'quota_project_id', None) == PROJECT}))
    for with_quota in (False, True):
        selected = credential.with_quota_project(PROJECT) if with_quota else credential
        class PilotCredential(credentials.Base):
            def get_credential(self):
                return selected
        app = firebase_admin.initialize_app(PilotCredential(), {'projectId': PROJECT, 'httpTimeout': 10}, name='diagnostic-' + str(with_quota))
        try:
            record = auth.get_user(UID, app=app)
            print(json.dumps({'stage': 'firebase_user_lookup', 'explicit_quota': with_quota,
                              'found': record.uid == UID, 'disabled': record.disabled}))
        except Exception as error:
            result = {'stage': 'firebase_user_lookup', 'explicit_quota': with_quota, 'error_type': type(error).__name__}
            message = str(error).lower()
            result['hints'] = {label: phrase in message for label, phrase in {
                'service_usage_permission': 'serviceusage.services.use',
                'api_disabled': 'disabled',
                'api_not_used': 'has not been used',
                'quota_project_required': 'quota project',
                'end_user_credentials': 'end user credentials',
                'permission_denied': 'permission',
                'identity_toolkit': 'identitytoolkit',
            }.items()}
            response = getattr(error, 'http_response', None)
            if response is not None:
                result['http_status'] = response.status_code
                try:
                    details = response.json().get('error', {}).get('details', [])
                    allowed = {'SERVICE_DISABLED', 'USER_PROJECT_DENIED', 'ACCESS_TOKEN_SCOPE_INSUFFICIENT', 'IAM_PERMISSION_DENIED', 'CONSUMER_INVALID', 'BILLING_DISABLED', 'CREDENTIALS_MISSING'}
                    result['reasons'] = [d['reason'] for d in details if d.get('reason') in allowed]
                except Exception:
                    pass
            print(json.dumps(result))
        finally:
            firebase_admin.delete_app(app)

if __name__ == '__main__':
    main()
