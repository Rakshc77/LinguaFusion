import asyncio
import io
import json
import wave
import httpx
import pytest
from cloud_api.pilot_providers import PilotProviders, ProviderFailure
from cloud_api.test_budget import TestBudget


def test_translation_routing_and_shared_hold(tmp_path):
    budget = TestBudget(tmp_path / 'budget.db')
    def handler(request):
        payload = json.loads(request.content)
        assert request.url.host == 'openrouter.ai'
        assert payload['provider']['allow_fallbacks'] is False
        assert payload['provider']['max_price']['completion'] == .05
        assert payload['model'] == 'mistralai/mistral-nemo'
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'Hallo'}}]})
    service = PilotProviders(budget, httpx.MockTransport(handler))
    assert asyncio.run(service.translate('fake-key', 'Hello', 'de')) == 'Hallo'
    budget.reserve('groq', 4990000)
    with pytest.raises(ValueError):
        asyncio.run(service.translate('fake-key', 'Hello', 'de'))


def test_failures_no_retry_or_refund(tmp_path):
    budget = TestBudget(tmp_path / 'budget.db')
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={'Location': 'https://example.com'})
    service = PilotProviders(budget, httpx.MockTransport(handler))
    with pytest.raises(ProviderFailure):
        asyncio.run(service.translate('fake-key', 'Hello', 'de'))
    assert len(requests) == 1
    budget.reserve('google_vision', 4990000)
    with pytest.raises(ValueError):
        budget.reserve('groq', 1)


def test_audio_and_ocr(tmp_path):
    wav = io.BytesIO()
    with wave.open(wav, 'wb') as writer:
        writer.setparams((1, 2, 16000, 0, 'NONE', 'NONE'))
        writer.writeframes(b'\x00' * 32000)
    def handler(request):
        if request.url.host == 'api.groq.com':
            assert b'whisper-large-v3-turbo' in request.content
            return httpx.Response(200, json={'text': ''})
        assert request.url.host == 'vision.googleapis.com'
        assert len(json.loads(request.content)['requests']) == 1
        return httpx.Response(200, json={'responses': [{'fullTextAnnotation': {'text': 'Hello'}}]})
    service = PilotProviders(TestBudget(tmp_path / 'budget.db'), httpx.MockTransport(handler))
    assert asyncio.run(service.transcribe('fake', wav.getvalue())) == ''
    assert asyncio.run(service.ocr('fake', b'\x89PNG\r\n\x1a\nfixture'))['text'] == 'Hello'  # ocr() now returns the whole annotation:
    # the geometry is what makes layout reconstruction possible.
    with pytest.raises(ValueError):
        asyncio.run(service.transcribe('fake', b'bad'))
    with pytest.raises(ValueError):
        asyncio.run(service.ocr('fake', b'%PDF'))


def test_reading_guide_preserves_native_and_rejects_native_script(tmp_path):
    replies = iter(['Namaste', 'नमस्ते'])
    def handler(request):
        payload = json.loads(request.content)
        assert payload['model'] == 'google/gemma-3-27b-it'
        assert not payload['provider']['allow_fallbacks']
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': next(replies)}}]})
    service = PilotProviders(TestBudget(tmp_path / 'budget.db'), httpx.MockTransport(handler))
    result = asyncio.run(service.romanize('fake', 'नमस्ते', 'hi'))
    assert result['native'] == 'नमस्ते' and result['romanized'] == 'Namaste'
    assert result['approximate'] is True
    with pytest.raises(ProviderFailure):
        asyncio.run(service.romanize('fake', 'नमस्ते', 'hi'))
    with pytest.raises(ValueError):
        asyncio.run(service.romanize('fake', 'Hello', 'en'))
