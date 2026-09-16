# Tennis Trader Alerts — container image
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data

# Persist bot-managed rules on a volume mounted at /app/data.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Provide keys at runtime — never bake them into the image:
#   docker run --rm \
#     -e LIVE_TENNIS_API_KEY=... \
#     -e TELEGRAM_BOT_TOKEN=... \
#     -v tta-data:/app/data \
#     tennis-trader-alerts
CMD ["python", "-m", "app"]
