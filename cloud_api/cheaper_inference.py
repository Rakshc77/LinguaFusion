"""Read-only Cheaper Inference discovery. No inference/paid fallback enabled.

Reference: https://api.cheaperinference.com/api-reference (2026-09-07).
The upstream is fixed so user input cannot redirect a server-side credential.
Free catalog status is informational, not a guarantee of zero billing.
"""
from decimal import Decimal, InvalidOperation
import re

import httpx
from fastapi import HTTPException

BASE_URL = 'https://api.cheaperinference.com/v1'


def billed_micro(data):
    """Exact provider-reported charge; missing/invalid must remain unknown."""
    if not isinstance(data, dict):
        return None
    billing = data.get('cheaper_inference')
    value = billing.get('billed_cost_usd') if isinstance(billing, dict) else None
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,12}\.\d{6}', value):
        return None
    return int(Decimal(value) * 1_000_000)


def _rate(value):
    # Do not turn absent pricing into a zero-cost claim.
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        rate = Decimal(value)
        if not rate.is_finite() or rate < 0 or rate > 1_000_000:
            return None
        return format(rate, 'f')
    except InvalidOperation:
        return None


def parse_catalog(data):
    if not isinstance(data, dict) or not isinstance(data.get('data'), list):
        raise ValueError('Invalid catalog')
    if len(data['data']) > 5000:
        raise ValueError('Catalog too large')
    result, seen = [], set()
    for item in data['data']:
        if not isinstance(item, dict) or item.get('type') != 'text':
            continue
        model = item.get('id')
        if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}', model) or model in seen:
            continue
        seen.add(model)
        pricing = item.get('pricing')
        pricing = pricing if isinstance(pricing, dict) else {}
        input_rate = _rate(pricing.get('input_per_million'))
        output_rate = _rate(pricing.get('output_per_million'))
        known = pricing.get('currency') == 'USD' and input_rate is not None and output_rate is not None
        free = known and item.get('is_free') is True and Decimal(input_rate) == 0 and Decimal(output_rate) == 0
        result.append({
            'id': model, 'provider': 'cheaper_inference',
            'pricing': 'free_catalog' if free else ('paid_api' if known else 'unknown'),
            'input_per_million_usd': input_rate if known else None,
            'output_per_million_usd': output_rate if known else None,
            'available': False,
            'reason': 'Discovery only. Inference and paid fallback are disabled; free eligibility must be verified.',
        })
    return result


async def discover_models(api_key, transport=None):
    """Key stays on backend. Never follow redirects or retry with another key."""
    if not api_key or not isinstance(api_key, str) or any(c.isspace() for c in api_key):
        raise HTTPException(503, 'Configure a valid provider key privately on the backend.')
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False, transport=transport) as client:
            async with client.stream('GET', BASE_URL + '/models',
                                     headers={'Authorization': 'Bearer ' + api_key}) as response:
                if response.status_code != 200:
                    raise HTTPException(502, 'Provider model discovery failed. Check key permissions and availability.')
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        raise ValueError('Catalog too large')
        import json
        return parse_catalog(json.loads(body))
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(502, 'Provider model discovery is temporarily unavailable.') from None
