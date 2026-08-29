FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

COPY pyproject.toml ./
COPY backend ./backend

RUN python -m pip install --no-cache-dir .

CMD ["python", "-m", "app.cli.run_cittati_worker"]
