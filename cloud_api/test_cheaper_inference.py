import asyncio
import httpx
import pytest
from fastapi import HTTPException
from cloud_api.cheaper_inference import billed_micro, parse_catalog, discover_models


def test_exact_billing_and_unknown_not_zero():
    assert billed_micro({'cheaper_inference': {'billed_cost_usd': '0.000001'}}) == 1
    assert billed_micro({'cheaper_inference': {'billed_cost_usd': '0.000000'}}) == 0
    for value in [None, 0, 'NaN', '-0.100000', '0.1', 'Infinity']:
        assert billed_micro({'cheaper_inference': {'billed_cost_usd': value}}) is None
    assert billed_micro({}) is None


def test_free_requires_explicit_flag_and_valid_zero_usd_prices():
    base = {'id': 'test/model', 'type': 'text', 'is_free': True,
            'pricing': {'currency': 'USD', 'input_per_million': '0', 'output_per_million': '0'}}
    row = parse_catalog({'data': [base]})[0]
    assert row['pricing'] == 'free_catalog' and not row['available']
    assert parse_catalog({'data': [dict(base, is_free=False)]})[0]['pricing'] == 'paid_api'
    for prices in [{}, {'currency': 'EUR', 'input_per_million': '0', 'output_per_million': '0'},
                   {'currency': 'USD', 'input_per_million': 'NaN', 'output_per_million': '0'}]:
        assert parse_catalog({'data': [dict(base, pricing=prices)]})[0]['pricing'] == 'unknown'
    assert parse_catalog({'data': [base, base, dict(base, type='image')]}) == [row]


def test_discovery_fixed_host_no_inference_or_redirect_following():
    requests = []
    def handler(request):
        requests.append(request)
        assert str(request.url) == 'https://api.cheaperinference.com/v1/models'
        assert request.method == 'GET'
        return httpx.Response(302, headers={'Location': 'https://untrusted.example/'})
    with pytest.raises(HTTPException) as error:
        asyncio.run(discover_models('test-secret', httpx.MockTransport(handler)))
    assert error.value.status_code == 502 and len(requests) == 1
    assert 'test-secret' not in error.value.detail


def test_success_and_oversized_response():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={'data': []}))
    assert asyncio.run(discover_models('test-secret', transport)) == []
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b' ' * 2_000_001))
    with pytest.raises(HTTPException):
        asyncio.run(discover_models('test-secret', transport))
