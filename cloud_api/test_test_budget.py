from concurrent.futures import ThreadPoolExecutor
import pytest
from cloud_api.test_budget import TestBudget


def test_shared_lifetime_cap_and_restart(tmp_path):
    path = tmp_path / 'budget.sqlite'
    budget = TestBudget(path)
    budget.reserve('openrouter', 2000000)
    budget.reserve('groq', 2000000)
    TestBudget(path).reserve('google_vision', 1000000)
    with pytest.raises(ValueError):
        TestBudget(path).reserve('groq', 1)


def test_atomic_cap(tmp_path):
    budget = TestBudget(tmp_path / 'budget.sqlite')
    def attempt(_):
        try:
            budget.reserve('groq', 1000000)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(12))) == 5


def test_unknown_cost_holds_and_settlement_is_idempotent(tmp_path):
    budget = TestBudget(tmp_path / 'budget.sqlite')
    request = budget.reserve('groq', 5000000)
    budget.settle(request, None)
    with pytest.raises(ValueError):
        budget.reserve('groq', 1)
    budget.settle(request, 1000000)
    budget.settle(request, 0)
    budget.reserve('google_vision', 4000000)
    with pytest.raises(ValueError):
        budget.reserve('groq', 1)


def test_reject_bad_reservations(tmp_path):
    budget = TestBudget(tmp_path / 'budget.sqlite')
    for value in [0, -1, True, 1.5]:
        with pytest.raises(ValueError):
            budget.reserve('groq', value)
    with pytest.raises(ValueError):
        budget.reserve('hosting', 1)


def test_summary_distinguishes_reserved_from_recorded(tmp_path):
    budget = TestBudget(tmp_path / 'budget.sqlite')
    first = budget.reserve('groq', 10000)
    budget.reserve('google_vision', 10000)
    budget.settle(first, 500)
    report = budget.summary()
    assert report['recorded_micro_usd'] == 500
    assert report['reserved_micro_usd'] == 10000
    assert report['unreconciled_requests'] == 1
    assert report['remaining_micro_usd'] == 4989500
