"""The browser's WAV encoder and the backend's validator must agree exactly.

They are written in different languages against the same spec, which is exactly
where a format contract silently drifts. This generates audio with the real
JavaScript encoder and feeds it to the real Python adapter.
"""
import asyncio
import json
import pathlib
import shutil
import subprocess

import httpx
import pytest

from cloud_api.pilot_providers import PilotProviders
from cloud_api.test_budget import TestBudget

WEB = pathlib.Path(__file__).parent / 'web'
node = shutil.which('node')
pytestmark = pytest.mark.skipif(node is None, reason='node is required for the cross-language check')


def encode_with_browser_code(seconds, source_rate):
    """Run the shipped wav.mjs to produce bytes, exactly as a phone would."""
    script = f'''
    import {{ buildWav }} from './wav.mjs';
    const rate = {source_rate};
    const samples = new Float32Array(Math.round({seconds} * rate));
    for (let i = 0; i < samples.length; i++) samples[i] = Math.sin(2 * Math.PI * 440 * i / rate) * 0.5;
    process.stdout.write(Buffer.from(buildWav([samples], rate)).toString('base64'));
    '''
    generator = WEB / '_contract_probe.mjs'
    generator.write_text(script, encoding='utf-8')
    try:
        result = subprocess.run([node, str(generator)], capture_output=True, text=True,
                                cwd=str(WEB), timeout=120, check=True)
    finally:
        generator.unlink(missing_ok=True)
    import base64
    return base64.b64decode(result.stdout)


@pytest.mark.parametrize('seconds,source_rate', [(1, 48000), (2, 44100), (0.5, 16000), (5, 22050)])
def test_browser_encoded_audio_is_accepted_by_the_backend(tmp_path, seconds, source_rate):
    audio = encode_with_browser_code(seconds, source_rate)
    sent = {}

    def handler(request):
        sent['bytes'] = len(request.content)
        return httpx.Response(200, json={'text': 'ok'})

    service = PilotProviders(TestBudget(tmp_path / 'b.sqlite'), httpx.MockTransport(handler))
    # The adapter's own validation runs before dispatch; reaching the transport
    # at all proves the file satisfied every check it makes.
    assert asyncio.run(service.transcribe('fake-key', audio)) == 'ok'
    assert sent['bytes'] > 0


def test_a_full_length_recording_still_passes_every_backend_check(tmp_path):
    audio = encode_with_browser_code(60, 48000)
    assert len(audio) <= 4_000_000, 'a 60 second recording must fit the upload limit'

    def handler(request):
        return httpx.Response(200, json={'text': ''})

    service = PilotProviders(TestBudget(tmp_path / 'b.sqlite'), httpx.MockTransport(handler))
    assert asyncio.run(service.transcribe('fake-key', audio)) == ''


def test_the_encoder_and_the_validator_agree_on_the_duration_limit(tmp_path):
    # 61 seconds must be refused by the browser rather than rejected after upload.
    generator = WEB / '_contract_probe_long.mjs'
    generator.write_text(
        "import { buildWav } from './wav.mjs';\n"
        "try { buildWav([new Float32Array(61 * 48000)], 48000); process.stdout.write('accepted'); }\n"
        "catch (e) { process.stdout.write('refused:' + e.message); }\n", encoding='utf-8')
    try:
        result = subprocess.run([node, str(generator)], capture_output=True, text=True,
                                cwd=str(WEB), timeout=120, check=True)
    finally:
        generator.unlink(missing_ok=True)
    assert result.stdout.startswith('refused:'), result.stdout
    assert '60 seconds' in result.stdout
