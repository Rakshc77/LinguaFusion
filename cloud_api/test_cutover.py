"""Readiness gate 5: one live ledger, never two.

The hazard: the local SQLite allowance and the managed cloud ledger each
permitting another US$5. These tests pin the three defences -- carry the balance
forward, close the local ledger, and stop the provider double-reserving once the
policy itself enforces the ceiling.
"""
import weakref
import tempfile

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from cloud_api.app import Settings, create_app
from cloud_api.pilot_capabilities import PILOT_HOLD_MICRO, ManagedBudget
from cloud_api.policy import LocalPolicy
from cloud_api.test_budget import TestBudget

AUTH = {'Authorization': 'Bearer valid'}


def verify(token):
    if token == 'valid':
        return {'uid': 'friend'}
    raise HTTPException(401, 'Invalid token')


def test_carry_forward_counts_unresolved_holds_as_spent(tmp_path):
    budget = TestBudget(tmp_path / 'b.sqlite')
    first = budget.reserve('openrouter', 10000)
    budget.reserve('groq', 10000)
    budget.settle(first, 4000)
    # 4000 recorded + 10000 still held. An unresolved hold may yet be billed, so
    # it must carry forward as spent rather than become available again.
    assert budget.carry_forward_micro() == 14000


def test_cutover_closes_local_spending_permanently(tmp_path):
    path = tmp_path / 'b.sqlite'
    budget = TestBudget(path)
    budget.reserve('openrouter', 10000)
    assert budget.cutover_at() is None

    stamp = budget.mark_cutover('moved to managed ledger')
    assert stamp and budget.cutover_at() == stamp

    with pytest.raises(ValueError, match='closed at cutover'):
        budget.reserve('openrouter', 10000)
    # A fresh handle on the same file must also refuse: this survives restarts.
    with pytest.raises(ValueError, match='closed at cutover'):
        TestBudget(path).reserve('groq', 10000)


def test_marking_cutover_twice_cannot_reopen_spending(tmp_path):
    budget = TestBudget(tmp_path / 'b.sqlite')
    first = budget.mark_cutover('one')
    assert budget.mark_cutover('two') == first, 'a retried cutover must not move the mark'
    with pytest.raises(ValueError):
        budget.reserve('groq', 1)


def test_rollback_is_available_only_as_an_explicit_admin_action(tmp_path):
    budget = TestBudget(tmp_path / 'b.sqlite')
    budget.mark_cutover('aborted')
    budget.clear_cutover()
    assert budget.cutover_at() is None
    assert budget.reserve('groq', 10000)


def test_summary_reports_cutover_state(tmp_path):
    budget = TestBudget(tmp_path / 'b.sqlite')
    assert budget.summary()['cutover_at'] is None
    budget.mark_cutover('done')
    assert budget.summary()['cutover_at'] is not None


def test_managed_budget_validates_providers_without_charging():
    budget = ManagedBudget()
    assert budget.reserve('openrouter', PILOT_HOLD_MICRO)
    for bad in ['hosting', 'openai', '']:
        with pytest.raises(ValueError):
            budget.reserve(bad, PILOT_HOLD_MICRO)
    for amount in [0, -1, 1.5, True]:
        with pytest.raises(ValueError):
            budget.reserve('groq', amount)
    assert budget.settle('anything', 500) is None


class CeilingPolicy:
    """Stands in for FirestorePolicy: it enforces the lifetime ceiling itself."""

    enforces_lifetime_ceiling = True

    def __init__(self):
        self.reservations = []
        self.settlements = []

    def require_access(self, uid):
        return None

    def reserve(self, uid, model=None, reserved_micro=0):
        self.reservations.append((uid, model, reserved_micro))
        return f'res-{len(self.reservations)}'

    def settle(self, reservation, actual):
        self.settlements.append((reservation, actual))

    def spending(self, uid=None):
        return {'month': '2026-09', 'estimated_spent_usd': '0.000000'}


def build_managed(handler):
    policy = CeilingPolicy()
    settings = Settings(project='p', allowed_uids=frozenset({'friend'}), enabled=True,
                        pilot_features=frozenset({'translate'}), openrouter_key='key')
    client = TestClient(create_app(settings, verify, httpx.MockTransport(handler), policy=policy))
    return client, policy


def test_a_ceiling_enforcing_policy_needs_no_local_ledger_file():
    def handler(request):
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
                                                      'message': {'content': 'Hallo'}}]})

    client, policy = build_managed(handler)
    with client:
        # No test_budget_path is configured, yet the capability is available:
        # the managed policy supplies the lifetime allowance.
        assert client.get('/capabilities', headers=AUTH).json()['features']['translation'] is True
        response = client.post('/api/translate', headers=AUTH,
                               data={'text': 'Hello', 'target_lang': 'de', 'paid_consent': 'true'})
    assert response.status_code == 200
    # THE point of gate 5: exactly one reservation for one request. A second one
    # here would charge the same dispatch twice and halve the real allowance.
    assert len(policy.reservations) == 1, policy.reservations
    assert policy.reservations[0][2] == PILOT_HOLD_MICRO


def test_a_local_policy_still_requires_the_separate_lifetime_ledger():
    directory = tempfile.TemporaryDirectory()
    policy = LocalPolicy(directory.name + '/p.sqlite3', ['friend'])
    policy.update('owner', 'friend', True, 100, 1_000_000)
    assert policy.enforces_lifetime_ceiling is False
    settings = Settings(project='p', allowed_uids=frozenset({'friend'}), enabled=True,
                        pilot_features=frozenset({'translate'}), openrouter_key='key')
    client = TestClient(create_app(settings, verify, None, policy=policy))
    weakref.finalize(client, directory.cleanup)
    with client:
        # Without a lifetime ledger there is no shared cap, so the capability
        # must stay unavailable rather than run uncapped.
        assert client.get('/capabilities', headers=AUTH).json()['features']['translation'] is False
        assert client.post('/api/translate', headers=AUTH,
                           data={'text': 'Hi', 'target_lang': 'de', 'paid_consent': 'true'}).status_code == 503


def test_master_ai_switch_disables_every_paid_capability():
    """LF_CLOUD_AI_ENABLED=0 must stop the /api/* routes, not just /translate."""
    policy = CeilingPolicy()
    settings = Settings(project='p', allowed_uids=frozenset({'friend'}),
                        enabled=False,  # the master switch is OFF
                        pilot_features=frozenset({'translate', 'pronounce'}),
                        openrouter_key='key')
    client = TestClient(create_app(settings, verify, httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(AssertionError('dispatched with paid AI off'))), policy=policy))
    with client:
        features = client.get('/capabilities', headers=AUTH).json()['features']
        assert features['translation'] is False and features['pronunciation'] is False
        for path, data in [('/api/translate', {'text': 'Hi', 'target_lang': 'de'}),
                           ('/api/pronounce', {'text': 'नमस्ते', 'language': 'hi'})]:
            response = client.post(path, headers=AUTH, data={**data, 'paid_consent': 'true'})
            assert response.status_code == 503, (path, response.status_code)
    assert policy.reservations == [], 'nothing may be reserved while paid AI is off'


def test_a_provider_failure_is_logged_with_its_reason_but_not_returned(caplog):
    """A 502 must be diagnosable from the logs without leaking anything."""
    import logging

    def failing(request):
        return httpx.Response(503, json={'error': 'upstream capacity'})

    client, policy = build_managed(failing)
    with caplog.at_level(logging.WARNING, logger='linguafusion.cloud'), client:
        response = client.post('/api/translate', headers=AUTH,
                               data={'text': 'Hello', 'target_lang': 'de', 'paid_consent': 'true'})
    assert response.status_code == 502
    assert 'retained' in response.json()['detail']
    logged = ' '.join(r.getMessage() for r in caplog.records)
    assert 'provider_failure' in logged, 'an outage must be diagnosable server-side'
    assert 'openrouter' in logged and '503' in logged, logged
    # The caller learns nothing about the upstream, and no body is logged.
    assert 'upstream capacity' not in response.text
    assert 'upstream capacity' not in logged


def test_only_reviewed_translation_models_can_be_chosen():
    from cloud_api.pilot_capabilities import TRANSLATION_MODELS

    def handler(request):
        import json as _json
        assert _json.loads(request.content)['model'] == 'google/gemma-3-27b-it'
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
                                                      'message': {'content': 'Hallo'}}]})

    client, policy = build_managed(handler)
    with client:
        chosen = client.post('/api/translate', headers=AUTH,
                             data={'text': 'Hello', 'target_lang': 'de', 'paid_consent': 'true',
                                   'model': 'google/gemma-3-27b-it'})
        assert chosen.status_code == 200, chosen.text
        assert chosen.json()['model'] == 'google/gemma-3-27b-it'
        # The ledger must name the model that actually cost the money.
        assert policy.reservations[-1][1] == 'pilot:openrouter/google/gemma-3-27b-it'

        # An unreviewed model is refused, never quietly swapped for the default:
        # returning a result from a different model than asked for misreports it.
        for bad in ['openai/gpt-4', 'anything', '../etc/passwd']:
            refused = client.post('/api/translate', headers=AUTH,
                                  data={'text': 'Hello', 'target_lang': 'de',
                                        'paid_consent': 'true', 'model': bad})
            assert refused.status_code == 422, bad
    assert len(policy.reservations) == 1, 'a refused model must not reserve anything'
    # Not a fixed list -- models get added. What must hold is that every one is
    # priced-capped, and that the cap stays modest: the flat US$0.01 hold has to
    # keep covering a full-page request at the dearest option.
    assert TRANSLATION_MODELS, 'there must be at least one approved model'
    for identifier, model in TRANSLATION_MODELS.items():
        cap = model.get('max_price')
        assert isinstance(cap, float) and 0 < cap <= 1.0, f'{identifier} has an unreasonable cap: {cap}'
        assert '/' in identifier, f'{identifier} is not an OpenRouter model id'


def test_capabilities_advertises_the_choosable_models():
    client, _ = build_managed(lambda request: httpx.Response(200, json={}))
    with client:
        body = client.get('/capabilities', headers=AUTH).json()
    ids = [model['id'] for model in body['translation_models']]
    assert 'mistralai/mistral-nemo' in ids and 'google/gemma-3-27b-it' in ids
    assert body['default_translation_model'] in ids
    for model in body['translation_models']:
        assert model['name'] and model['note'], 'each choice needs a name and a plain-language note'


def test_each_model_carries_guidance_the_page_can_show():
    client, _ = build_managed(lambda request: httpx.Response(200, json={}))
    with client:
        body = client.get('/capabilities', headers=AUTH).json()
    for model in body['translation_models']:
        for field in ['name', 'note', 'best_for', 'weaker_at', 'speed', 'cost']:
            assert model.get(field), f'{model["id"]} is missing {field}'
    # The notes are reputations, not measurements on this app's own text, and
    # the page must be told so it can say it rather than implying evidence.
    assert body['model_guidance_is_measured'] is False


def test_the_price_ceiling_sent_upstream_matches_the_chosen_model():
    # provider.only pins DeepInfra and max_price refuses anything dearer. A cap
    # copied from the wrong model would either reject a working model outright
    # or let a dearer one through unnoticed.
    from cloud_api.pilot_providers import TRANSLATION_MODELS
    seen = {}

    def handler(request):
        import json as _json
        payload = _json.loads(request.content)
        seen[payload['model']] = payload['provider']
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
                                                      'message': {'content': 'ok'}}]})

    client, _ = build_managed(handler)
    with client:
        for identifier in TRANSLATION_MODELS:
            response = client.post('/api/translate', headers=AUTH,
                                   data={'text': 'Hello', 'target_lang': 'de',
                                         'paid_consent': 'true', 'model': identifier})
            assert response.status_code == 200, (identifier, response.text)

    for identifier, model in TRANSLATION_MODELS.items():
        provider = seen[identifier]
        assert provider['only'] == ['deepinfra'], identifier
        assert provider['allow_fallbacks'] is False, identifier
        assert provider['max_price']['completion'] == model['max_price'], identifier
        assert provider['data_collection'] == 'deny', identifier


def test_there_is_no_date_based_hard_stop_left():
    # A fixed cut-off date refused every request for everyone once it passed,
    # taking the service down without warning. Price review is a reminder now.
    import pathlib
    import re
    source = (pathlib.Path(__file__).parent / 'pilot_providers.py').read_text(encoding='utf-8')
    dispatch = source[source.index('async def _post'):source.index('def _headers')]
    assert 'date.today()' not in dispatch, 'dispatch must not refuse on a date'
    assert 'raise ProviderFailure' in source, 'real provider failures are still raised'


def test_the_price_review_reminder_recurs_monthly_and_can_be_acknowledged():
    from datetime import date
    from cloud_api.pilot_providers import review_due

    # Not due the day after a review.
    assert review_due(date(2026, 9, 9), '2026-09-08')['due'] is False
    # Due when the day comes round in the next month.
    assert review_due(date(2026, 10, 8), '2026-09-08')['due'] is True
    # Acknowledging on the day moves it on rather than re-arming immediately.
    acknowledged = review_due(date(2026, 10, 8), '2026-10-08')
    assert acknowledged['due'] is False and acknowledged['next_due'] == '2026-11-08'
    # A month too short for the 31st must not raise.
    assert review_due(date(2027, 3, 1), '2027-01-31')['next_due'] == '2027-02-08'
    # Nonsense never breaks dispatch; it falls back to the known review date.
    assert review_due(date(2026, 9, 9), 'not-a-date')['due'] is False


def test_only_the_owner_is_shown_the_review_reminder():
    # Everyone else keeps working: a pricing review is the owner's job, and
    # other people cannot act on it.
    client, _ = build_managed(lambda request: httpx.Response(200, json={}))
    with client:
        body = client.get('/capabilities', headers=AUTH).json()
    assert body['price_review'] is None, 'a non-owner must not be nagged about prices'


def test_recent_provider_failures_are_visible_without_leaking_user_content():
    from cloud_api.pilot_capabilities import record_failure, recent_failures
    record_failure('translate', 'openrouter returned HTTP 503; reservation retained.')
    newest = recent_failures()[0]
    assert newest['capability'] == 'translate'
    assert '503' in newest['reason'] and newest['at']
    # The reason comes from the adapter, which carries provider and status only.
    assert 'Bearer' not in newest['reason']
