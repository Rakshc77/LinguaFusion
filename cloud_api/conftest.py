"""Deterministic dates for tests of the legacy, mocked paid-model route."""
from datetime import date

import pytest

from cloud_api import models


@pytest.fixture
def reviewed_model_prices(monkeypatch):
    """Exercise provider/budget behavior within the catalog's review window."""
    class ReviewedDate(date):
        @classmethod
        def today(cls):
            return date.fromisoformat(models.PRICE_REVIEWED)

    monkeypatch.setattr(models, 'date', ReviewedDate)
