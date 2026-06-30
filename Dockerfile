# syntax=docker/dockerfile:1

# ---- Builder stage ----
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1

WORKDIR /build

COPY pyproject.toml ./
COPY src/ src/

RUN pip install --no-cache-dir --prefix=/install .

# ---- Runtime stage ----
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /install /usr/local
COPY src/ src/
COPY alembic.ini .
COPY alembic/ alembic/

ENV PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"

CMD ["uvicorn", "ticketmaster.main:app", "--host", "0.0.0.0", "--port", "8000"]
