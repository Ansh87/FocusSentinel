FROM python:3.11-slim

WORKDIR /app

COPY services/notification-worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/notification-worker /app

CMD ["python", "-m", "app.worker"]
