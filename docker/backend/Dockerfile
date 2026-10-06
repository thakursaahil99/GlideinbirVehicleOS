# Vehicle Service CRM — backend image (built by Sahil Thakur)
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app

ARG REQUIREMENTS=dev
COPY backend/requirements /tmp/requirements
RUN pip install -r /tmp/requirements/${REQUIREMENTS}.txt

COPY --chown=app:app backend /app
COPY --chown=app:app docker/backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /app/media /app/staticfiles && chown -R app:app /app/media /app/staticfiles

USER app
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
