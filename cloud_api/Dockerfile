FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY cloud_api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home appuser
COPY cloud_api/__init__.py cloud_api/app.py /app/cloud_api/
COPY cloud_api/policy.py /app/cloud_api/policy.py
COPY cloud_api/firestore_policy.py /app/cloud_api/firestore_policy.py
COPY cloud_api/models.py /app/cloud_api/models.py
COPY cloud_api/pilot_capabilities.py /app/cloud_api/pilot_capabilities.py
COPY cloud_api/ocr_layout.py /app/cloud_api/ocr_layout.py
COPY cloud_api/access_requests.py /app/cloud_api/access_requests.py
COPY cloud_api/pilot_providers.py /app/cloud_api/pilot_providers.py
# Ledger CODE only. No local ledger file, credential or ADC is ever copied.
COPY cloud_api/test_budget.py /app/cloud_api/test_budget.py
COPY cloud_api/web/ /app/cloud_api/web/
COPY backend/request_limits.py /app/backend/request_limits.py
USER 10001
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "cloud_api.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
