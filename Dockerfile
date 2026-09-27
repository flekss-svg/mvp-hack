FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && addgroup --system app \
    && adduser --system --ingroup app --home /app app

COPY --chown=app:app app/ ./app/
COPY --chown=app:app ml_service/ ./ml_service/
COPY --chown=app:app scripts/ ./scripts/
COPY --chown=app:app models/ ./models/
COPY --chown=app:app reports/ ./reports/
COPY --chown=app:app data/processed/ ./data/processed/

USER app

CMD ["python", "-m", "uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
