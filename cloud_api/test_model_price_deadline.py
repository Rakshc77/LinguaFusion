"""The production pricing deadline must still fail closed after it expires."""
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from cloud_api import models


@pytest.mark.parametrize('offset,available', [(-1, True), (0, True), (1, False)])
def test_model_price_review_boundary(monkeypatch, offset, available):
    day = date.fromisoformat(models.PRICE_VALID_UNTIL) + timedelta(days=offset)

    class TestDate(date):
        @classmethod
        def today(cls):
            return day

    monkeypatch.setattr(models, 'date', TestDate)
    model = next(iter(models.PAID))
    item = next(item for item in models.catalog({model}, True) if item['id'] == model)
    assert item['available'] is available
    if available:
        assert models.reserve_cost(model, 'hello') > 0
    else:
        with pytest.raises(HTTPException) as error:
            models.reserve_cost(model, 'hello')
        assert error.value.status_code == 503
        assert 'review model prices' in error.value.detail
