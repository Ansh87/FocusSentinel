FROM python:3.11-slim

WORKDIR /app

COPY services/api/requirements.txt ./requirements.txt
COPY packages/rules-engine /packages/rules-engine
COPY packages/activity-classifier /packages/activity-classifier

RUN pip install --no-cache-dir -r requirements.txt

COPY services/api /app

EXPOSE 8000
# Shell form (not exec-array form) so $PORT actually expands — Railway (and
# most PaaS platforms) assign a dynamic port via this env var at runtime and
# route traffic to whatever the container binds. Falls back to 8000 for
# `docker compose up` / plain `docker run`, where PORT is unset.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
