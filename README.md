# Ticketmaster MVP

[![Lint](https://github.com/iliazlobin/sd-ticketmaster-backend-mvp/actions/workflows/lint.yml/badge.svg)](https://github.com/iliazlobin/sd-ticketmaster-backend-mvp/actions/workflows/lint.yml)
[![CI](https://github.com/iliazlobin/sd-ticketmaster-backend-mvp/actions/workflows/ci.yml/badge.svg)](https://github.com/iliazlobin/sd-ticketmaster-backend-mvp/actions/workflows/ci.yml)
[![Functional](https://github.com/iliazlobin/sd-ticketmaster-backend-mvp/actions/workflows/functional.yml/badge.svg)](https://github.com/iliazlobin/sd-ticketmaster-backend-mvp/actions/workflows/functional.yml)

Event ticketing REST API — browse, search, reserve, and book seats. Python 3.12, FastAPI, PostgreSQL 16, Redis 7.

## Quickstart

**Docker Compose** (requires Docker Engine 24+):

```bash
git clone https://github.com/iliazlobin/sd-ticketmaster-backend-mvp.git
cd sd-ticketmaster-backend-mvp
APP_PORT=8010 docker compose up -d --build
curl http://localhost:8010/healthz
# > {"status":"ok"}
```

**Local development** (requires Python 3.11+, PostgreSQL 16, Redis 7):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn ticketmaster.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/healthz
# > {"status":"ok"}
```

## API Reference

Base URL: `http://localhost:8000` (or `$APP_PORT` in Docker Compose).

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/events?category=&date_from=&date_to=&page=` | Browse events with optional filters and pagination (page size 20) |
| `GET` | `/events/{event_id}/seats` | View seat map with real-time availability per seat |
| `GET` | `/search?q=` | Full-text search across event name, performer, and venue |
| `POST` | `/reservations` | Reserve seats atomically with 10-minute hold. Body: `{event_id, seat_ids, user_id, idempotency_key}` |
| `POST` | `/reservations/{reservation_id}/confirm` | Confirm a held reservation and simulate payment. Body: `{owner_token}` |
| `GET` | `/bookings/{booking_id}` | Retrieve booking details including seat assignments |
| `GET` | `/healthz` | Health check — returns `{"status":"ok"}` |

**Error responses:** `404` (not found), `403` (wrong owner_token), `409` (conflict — seat already held/sold, or already confirmed), `410` (expired reservation), `422` (validation error).

**Idempotency:** `POST /reservations` accepts a client-supplied `idempotency_key`. Duplicate submission with same payload returns `200` with the original reservation. Different payload with same key returns `422`.

A full API reference with request/response shapes is in [DESIGN.md](DESIGN.md).

## Configuration

All settings via environment variables. Copy `.env.example` to `.env` to override defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `LOG_LEVEL` | `info` | Logging level |
| `DATABASE_URL` | `postgresql+asyncpg://ticketmaster:ticketmaster@localhost:5432/ticketmaster` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `SEAT_HOLD_TTL` | `600` | Seat hold TTL in seconds (10 minutes) |
| `APP_PORT` | `8010` | Host port in Docker Compose mode |
| `SEED_DEMO_DATA` | `0` | Set to `1` to insert 1 demo event + 60 seats on startup |

In Docker Compose, only `APP_PORT` is typically overridden. Internal services communicate over the compose network and do not publish host ports.

## Testing

Three test suites:

| Suite | Command | Requires |
|-------|---------|----------|
| **Unit** | `pytest tests/unit/ -v` | Nothing (mocked DB/Redis) |
| **Functional** | `pytest tests/functional/ -v` | Running app at `API_BASE_URL` (default `http://localhost:8095`) |
| **Acceptance** | `API_BASE_URL=http://localhost:8010 pytest verify/acceptance/ -v` | Running stack with seeded data |

Acceptance tests require a running stack with demo data and short hold TTL for FR-7 (expired hold release):

```bash
SEED_DEMO_DATA=1 SEAT_HOLD_TTL=5 docker compose up -d --build
API_BASE_URL=http://localhost:8010 pytest verify/acceptance/ -v
```

## Architecture

```
Client (REST) > FastAPI > SQLAlchemy > PostgreSQL (durable state)
                       > redis-py  > Redis (seat locks, 600s TTL)
```

Monolithic REST API with Redis fast-path seat-lock fencing. Three-layer oversell prevention:

1. **Redis `SET NX EX`** — sub-millisecond atomic lock acquisition per seat
2. **PostgreSQL OCC** — `UPDATE ... WHERE version=? AND status='held'` catches TTL edge cases
3. **`UNIQUE(seat_id)` on `booking_seats`** — database-level final guarantee

Key design choices: PostgreSQL `tsvector` + GIN index for full-text search (no Elasticsearch in MVP), simulated payment (no real Stripe), Redis TTL for automatic hold release, database `UNIQUE` constraint on `idempotency_key` for at-most-once reservation.

## Project Layout

```
src/ticketmaster/          Application package
  main.py                  FastAPI app factory, lifespan, /healthz
  config.py                pydantic-settings
  database.py              Async SQLAlchemy engine + session
  redis.py                 Async Redis client
  seed.py                  Idempotent demo-data seeder
  models/                  SQLAlchemy ORM: Event, Seat, Reservation, Booking, BookingSeat
  schemas/                 Pydantic v2 request/response DTOs
  routers/                 Thin FastAPI route handlers
  services/                Business logic (event search, seat locking, booking)
tests/
  unit/                    Isolated logic with mocked DB/Redis
  functional/              In-process endpoint scenarios
verify/acceptance/         Black-box HTTP acceptance suite (one file per FR)
alembic/                   Database migrations (3 revisions)
.github/workflows/         CI: lint, unit tests, functional tests
docker-compose.yml         PostgreSQL 16 + Redis 7 + app
Dockerfile                 Multi-stage Python 3.12-slim
DEPLOY.md                  Full deploy & operations guide
```

## Limitations

- **No real payment integration.** Confirm simulates payment; `total_cents` is always 0.
- **No interactive seat map rendering.** Seat map data is JSON-only; no SVG/Canvas tiles.
- **No waiting room / queue.** The API has no admission control for high-traffic onsales.
- **No real geo search.** `lat`/`lon`/`radius` query params are accepted but ignored.
- **No authentication.** `user_id` is an opaque UUID with no auth, no FK to a users table.
- **Hold expiry via polling.** Expired holds release lazily when `GET /events/{id}/seats` is called, not via a background scheduler.
- **Single-node only.** No sharding, no horizontal scaling, no replication configured.
- **PostgreSQL full-text search only.** No Elasticsearch for multi-language ranking or faceted navigation.
