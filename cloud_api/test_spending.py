from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from cloud_api.app import Settings, create_app
from cloud_api.models import usage_cost, reserve_cost, budget_micro, catalog
from cloud_api.policy import LocalPolicy

def test_prices_cached_usage_and_missing_usage():
    assert usage_cost('gpt-5.6-luna', {'input_tokens':1000, 'output_tokens':1000, 'input_tokens_details':{'cached_tokens':500}}) == 1310
    assert usage_cost('gpt-5.6-luna', None) is None
    assert usage_cost('gpt-5.6-luna', {'input_tokens':-1,'output_tokens':0}) is None
    assert reserve_cost('gpt-5.6-luna', 'أهلاً') > 0
    assert budget_micro('0.01') == 10000
    for value in ['NaN', 'Infinity', '-1', '0.001', '1001']:
        with pytest.raises(HTTPException): budget_micro(value)
    assert all(not m['available'] for m in catalog([], False))

def test_atomic_money_budget_and_persistent_unresolved_holds(tmp_path):
    path = tmp_path / 'policy.db'
    policy = LocalPolicy(path, ['friend'])
    policy.update('owner','friend',True,100,10000)
    def attempt(_):
        try: return LocalPolicy(path).reserve('friend','gpt-5.6-luna',4000)
        except HTTPException: return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = [item for item in pool.map(attempt,range(12)) if item]
    assert len(ids) == 2
    assert LocalPolicy(path).spending('friend')['unresolved_reserved_usd'] == '0.008000'
    policy.settle(ids[0], 1000)
    policy.settle(ids[0], 0)  # Duplicate settlement cannot refund usage.
    assert policy.spending('friend')['estimated_spent_usd'] == '0.001000'
    assert policy.spending('friend')['remaining_usd'] == '0.005000'

def test_selection_consent_cost_recording_and_zero_budget(tmp_path):
    policy = LocalPolicy(tmp_path / 'policy.db', ['friend'])
    settings = Settings(enabled=True,model='gpt-5.6-luna',api_key='fake', allowed_models=frozenset({'gpt-5.6-luna','gpt-5.6-terra'}))
    calls=[]
    def handler(request):
        import json
        calls.append(json.loads(request.content)['model'])
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':100,'output_tokens':20},'output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Hallo'}]}]})
    with TestClient(create_app(settings,verifier=lambda token:{'uid':token},policy=policy,transport=httpx.MockTransport(handler))) as client:
        headers={'Authorization':'Bearer friend'}
        data={'text':'hello','model':'gpt-5.6-terra','paid_consent':'true'}
        assert client.post('/translate',headers=headers,data=data).status_code == 429
        assert calls == []
        policy.update('owner','friend',True,100,1_000_000)
        assert client.post('/translate',headers=headers,data=dict(data,paid_consent='false')).status_code == 422
        assert client.post('/translate',headers=headers,data=dict(data,model='gpt-5.6-sol')).status_code == 403
        assert client.post('/translate',headers=headers,data=dict(data,model='local-argos')).status_code == 422
        result=client.post('/translate',headers=headers,data=data)
        assert result.status_code == 200
        assert calls == ['gpt-5.6-terra']
        assert result.json()['spending']['estimated_spent_usd'] == '0.000440'
        assert client.get('/usage',headers=headers).json()['unresolved_reserved_usd'] == '0.000000'
        assert client.get('/usage').status_code == 401


def test_a_successful_request_settles_its_hold_against_reported_usage():
    # Every hold used to stand forever: 39 requests showed $0.39 held and
    # $0.00 spent, so the ledger could not answer what anything cost, and the
    # shared allowance drained about fifty times faster than real spending.
    import asyncio
    from cloud_api.pilot_capabilities import PILOT_HOLD_MICRO
    from cloud_api.pilot_providers import LAST_USAGE, token_cost_micro

    model = 'mistralai/mistral-small-24b-instruct-2501'
    usage = {'prompt_tokens': 600, 'completion_tokens': 600}
    actual = token_cost_micro(model, usage)
    assert actual is not None and 0 < actual < PILOT_HOLD_MICRO, (
        'the whole point is that a real call costs far less than the hold')

    settled = {}

    class Policy:
        def reserve(self, uid, charge_id, micro):
            return 'reservation-1'

        def settle(self, reservation, actual_micro):
            settled[reservation] = actual_micro

    from cloud_api.pilot_capabilities import PilotGateway
    # available() requires providers to be truthy as well as the feature being
    # enabled; the object itself is never touched on this path.
    gateway = PilotGateway(providers=object(), policy=Policy(),
                           enabled_features={'translate'}, paid_ai_enabled=True)

    async def succeed():
        LAST_USAGE.set({'model': model, 'usage': usage})
        return 'hola'

    assert asyncio.run(gateway.run('translate', 'uid-1', succeed)) == 'hola'
    assert settled.get('reservation-1') == actual, settled
    assert settled['reservation-1'] < PILOT_HOLD_MICRO, 'the hold was not reduced'


def test_a_provider_that_reports_nothing_keeps_its_hold():
    # An unresolved hold says "this cost at most a cent", which is true.
    # Settling at a guess would state something we do not know.
    from cloud_api.pilot_providers import token_cost_micro
    assert token_cost_micro('any-model', None) is None
    assert token_cost_micro('any-model', {'prompt_tokens': 'many'}) is None
    assert token_cost_micro('any-model', {}) is None


def test_the_recorded_cost_never_rounds_down_to_free():
    # A short call costs a fraction of a micro-dollar. Rounding it to zero
    # would make real usage look free and hide it from the ledger entirely.
    from cloud_api.pilot_providers import token_cost_micro
    assert token_cost_micro('mistralai/mistral-nemo',
                            {'prompt_tokens': 1, 'completion_tokens': 1}) >= 1
