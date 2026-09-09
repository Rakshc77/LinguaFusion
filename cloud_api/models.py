"""Reviewed model catalog and USD estimates; not provider invoice accounting."""
from datetime import date
from decimal import Decimal, ROUND_CEILING
from fastapi import HTTPException

PRICE_REVIEWED = '2026-09-07'
PRICE_VALID_UNTIL = '2026-10-07'
MAX_OUTPUT = 2048
# USD per million tokens, standard service tier. No tools or long prompts.
PAID = {
    'gpt-5.6-luna': ('GPT-5.6 Luna', '0.20', '0.02', '1.20'),
    'gpt-5.6-terra': ('GPT-5.6 Terra', '2.00', '0.20', '12.00'),
    'gpt-5.6-sol': ('GPT-5.6 Sol', '4.00', '0.40', '20.00'),
}

def require_model(model):
    if model not in PAID:
        raise HTTPException(422, 'Choose a supported paid model.')
    if date.today().isoformat() > PRICE_VALID_UNTIL:
        raise HTTPException(503, 'The owner must review model prices before paid use resumes.')

def reserve_cost(model, text):
    require_model(model)
    # Byte count is a deliberately conservative text-token bound; additional
    # allowance covers our fixed instructions and protocol overhead. Reserve
    # the cache-write rate for all input rather than assuming cache discounts.
    input_bound = len(text.encode('utf-8')) + 2048
    _, input_rate, _, output_rate = PAID[model]
    return int((Decimal(input_bound) * Decimal(input_rate) * Decimal('1.25') + MAX_OUTPUT * Decimal(output_rate)).to_integral_value(rounding=ROUND_CEILING))

def usage_cost(model, usage):
    if not isinstance(usage, dict):
        return None
    input_tokens, output_tokens = usage.get('input_tokens'), usage.get('output_tokens')
    details = usage.get('input_tokens_details') or {}
    cached = details.get('cached_tokens', 0) if isinstance(details, dict) else None
    if any(type(n) is not int or n < 0 for n in (input_tokens, output_tokens, cached)) or cached > input_tokens:
        return None
    # Cache-write accounting is not established for this pilot yet. If reported,
    # keep the conservative hold instead of presenting a misleading cost.
    if any('write' in key and value for key, value in details.items()):
        return None
    _, input_rate, cache_rate, output_rate = PAID[model]
    micro = ((input_tokens - cached) * Decimal(input_rate) + cached * Decimal(cache_rate) + output_tokens * Decimal(output_rate))
    return int(micro.to_integral_value(rounding=ROUND_CEILING))

def usd(micro):
    return format(Decimal(micro) / Decimal(1_000_000), '.6f')

def budget_micro(value):
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0 or amount > 1000 or amount != amount.quantize(Decimal('.01')):
            raise ValueError()
        return int(amount * 1_000_000)
    except Exception:
        raise HTTPException(422, 'Budget must be USD 0–1000 with at most two decimal places.') from None

def catalog(allowed, enabled):
    result = [dict(id=key, name=item[0], pricing='paid_api', input_per_million_usd=item[1],
                   cached_input_per_million_usd=item[2], output_per_million_usd=item[3],
                   available=bool(enabled and key in allowed and date.today().isoformat() <= PRICE_VALID_UNTIL),
                   source='https://developers.openai.com/api/docs/models/' + key)
              for key, item in PAID.items()]
    result += [dict(id=key, name=name, pricing='no_api_fee', available=False,
                    reason='PC app only; not connected to this cloud pilot. Electricity and hardware costs still apply.')
               for key, name in [('local-nllb', 'NLLB-200 — local translation'), ('local-argos', 'Argos — local translation'), ('local-ollama', 'Ollama — local AI correction')]]
    return result
