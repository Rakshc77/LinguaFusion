"""Synthetic tests only; ADC tokens and raw upstream errors are never printed."""
import asyncio
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloud_api.pilot_providers import PilotProviders, ProviderFailure
from cloud_api.test_budget import TestBudget

async def main():
    root = Path(__file__).resolve().parents[1]
    samples = root / 'cloud_api/local-data/synthetic-tests'
    service = PilotProviders(TestBudget(root / 'cloud_api/local-data/combined-test-budget.sqlite3'))
    failed = False
    try:
        text = '' if '--ocr-only' in sys.argv else await service.transcribe(os.environ.get('LF_TEST_GROQ_KEY', ''), (samples / 'speech.wav').read_bytes())
        if '--ocr-only' not in sys.argv:
            print('Groq synthetic transcript:', text)
        if '--ocr-only' not in sys.argv and not all(word in text.lower() for word in ('train', 'ticket')):
            print('Speech semantic smoke check failed.')
            failed = True
    except (ProviderFailure, ValueError) as error:
        print('Speech:', str(error))
        failed = True
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession, Request
        credential, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        credential = credential.with_quota_project('linguafusion-f24fe')
        # Read-only project policy check; never print unrelated principals.
        with AuthorizedSession(credential) as session:
            response = session.post('https://cloudresourcemanager.googleapis.com/v1/projects/linguafusion-f24fe:getIamPolicy', json={}, timeout=20)
            member = 'serviceAccount:linguafusion-be@linguafusion-f24fe.iam.gserviceaccount.com'
            if response.status_code == 200:
                roles = [b['role'] for b in response.json().get('bindings', []) if member in b.get('members', []) and not b.get('condition')]
                print('Backend service account unconditional roles:', ', '.join(roles) or 'none')
            else:
                print('Service account IAM check unavailable; HTTP', response.status_code)
        credential.refresh(Request())
        text = await service.ocr(credential.token, (samples / 'ocr.png').read_bytes())
        print('Vision synthetic OCR:', text.strip())
        print('Vision used local developer ADC, NOT the deployment service account.')
        if '14:30' not in text or 'train' not in text.lower():
            print('OCR semantic smoke check failed.')
            failed = True
    except (ProviderFailure, ValueError) as error:
        print('Vision:', str(error))
        failed = True
    except Exception as error:
        print('Google credential/IAM check failed:', type(error).__name__)
        failed = True
    print('Each dispatched media request retains USD 0.01 as a reservation, not actual billed spend.')
    return 1 if failed else 0

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
