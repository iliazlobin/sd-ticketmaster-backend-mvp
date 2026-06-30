# Ticketmaster MVP — Deploy & Operations

Event ticketing REST API: Python 3.12 · FastAPI · PostgreSQL 16 · Redis 7 · Docker Compose.

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- Python 3.11+ (for local development without Docker)
- PostgreSQL 16 (if running without Docker)
- Redis 7 (if running without Docker)
- `make` or just shell

## Quickstart (Docker Compose)

From a clean checkout:

```bash
# 1. Set the host port (defaults to 8010; change if that port is taken)
export APP_PORT=8010

# 2. Build and start everything
docker compose up -d --build

# 3. Wait for healthy (all three services report healthy)
docker compose ps

# 4. Verify the app responds
python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8010/healthz').read())"
# → b'{"status":"ok"}'

# 5. Smoke-test an endpoint
curl -s http://localhost:8010/events?page=1 | python -m json.tool | head -20
```

The stack is up and serving on `http://localhost:$APP_PORT`.

## Environment

Copy `.env.example` to `.env` and uncomment any values you need to override.

| Variable | Default | Notes |
|---|---|---|
| `APP_PORT` | `8010` | Host port mapped to container port 8000 |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Container-internal port (leave as-is in compose) |
| `LOG_LEVEL` | `info` | uvicorn log level |
| `DATABASE_URL` | `postgresql+asyncpg://ticketmaster:ticketmaster@localhost:5432/ticketmaster` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `SEAT_HOLD_TTL` | `600` | Seat reservation hold in seconds (10 min) |
| `SEED_DEMO_DATA` | `0` | When `1`, the app inserts one demo event (60 available seats) on startup if the DB has no events. **Production leaves this unset/`0`.** |

**In Docker Compose**, only `APP_PORT` matters for a normal deploy — set it before `docker compose up`.  
Internal services (`db`, `redis`) communicate over the compose network and do NOT publish host ports.

### Acceptance / e2e mode (demo seed + short hold TTL)

The black-box acceptance suite (`verify/acceptance/`) discovers test data via `GET /events` (the public
API has no event-creation endpoint), and FR-7 verifies that expired holds release within a ~15s poll. So the
e2e run overrides two env vars — both already wired into `docker-compose.yml` as `${VAR:-default}` and into
`verify/manifest.env`'s `UP`:

```bash
SEED_DEMO_DATA=1 SEAT_HOLD_TTL=5 docker compose up -d --build
```

- `SEED_DEMO_DATA=1` → the startup `python -m ticketmaster.seed` inserts 1 event + 60 seats (idempotent; no-op if events exist).
- `SEAT_HOLD_TTL=5` → holds expire fast so FR-7's expired-hold-release assertion passes in bounded time.

A **production** deploy sets neither (real events already exist; the 600s hold is the real checkout window).

## Services

| Service | Image | Host Port | Internal Port | Healthcheck |
|---|---|---|---|---|
| `app` | Built from `Dockerfile` | `${APP_PORT:-8010}` | 8000 | `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"` |
| `db` | `postgres:16-alpine` | none | 5432 | `pg_isready -U ticketmaster` |
| `redis` | `redis:7-alpine` | none | 6379 | `redis-cli ping` |

### App healthcheck details

The runtime image is `python:3.12-slim` — no `curl` or `wget`.  
The healthcheck uses Python stdlib:

```
HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"
```

The `GET /healthz` endpoint returns `{"status": "ok"}` when the app, database, and Redis are all connected.

### Startup command

The compose `app` service runs a shell command that performs migrations, then starts uvicorn:

```bash
PYTHONPATH=/app alembic upgrade head &&
uvicorn ticketmaster.main:app --host 0.0.0.0 --port 8000
```

## Running locally (no Docker)

```bash
# 1. Create virtualenv and install
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Start PostgreSQL and Redis (your own instances or via docker compose up db redis)
#    Set DATABASE_URL and REDIS_URL in .env or env vars pointing to your instances.

# 3. Run migrations
DATABASE_URL=postgresql+asyncpg://ticketmaster:ticketmaster@localhost:5432/ticketmaster \
    alembic upgrade head

# 4. Start the app
uvicorn ticketmaster.main:app --host 0.0.0.0 --port 8000

# 5. Verify
curl -s http://localhost:8000/healthz
# → {"status":"ok"}
```

## Database Migrations

Alembic is used for schema management. Three migration files ship with the project:

- `001_initial_schema.py` — events, seats, reservations, bookings, booking_seats tables
- `002_search_index.py` — GIN index for PostgreSQL full-text search
- `003_fix_booking_seats_pk.py` — composite primary key fix

```bash
# Apply all pending migrations
alembic upgrade head

# Check current revision
alembic current

# Generate a new migration after model changes
alembic revision --autogenerate -m "description"
```

## Tests

Three test suites, each with a distinct purpose:

| Suite | Command | What it tests |
|---|---|---|
| Unit | `pytest tests/unit/ -v` | Isolated logic with mocked DB/Redis — no external services needed |
| Functional | `pytest tests/functional/ -v` | In-process endpoint scenarios against a real app instance |
| Acceptance | `API_BASE_URL=http://localhost:8010 pytest verify/acceptance/ -q` | Black-box HTTP tests against a running stack |

```bash
# Run everything (requires running app + DB + Redis)
pip install -e ".[dev]"
pytest tests/unit/ -v
pytest tests/functional/ -v
API_BASE_URL=http://localhost:8010 pytest verify/acceptance/ -v
```

## CI/CD

GitHub Actions workflows (`.github/workflows/`):

| Workflow | Triggers | What it does |
|---|---|---|
| `lint.yml` | push, PR, daily | `ruff check` + `ruff format --check` (v0.8.0). Copilot Code Review on PRs (advisory). |
| `ci.yml` | push, PR, daily | Unit tests (`pytest tests/unit/`) + manifest validation (sources `verify/manifest.env`). |
| `functional.yml` | push, PR, daily | Spins up PostgreSQL 16 service, runs `alembic upgrade head`, then `pytest tests/functional/ -v`. |

All workflows use `on: [push, pull_request]` plus a daily schedule at 06:00 UTC.

## Logs

```bash
# All services (last 100 lines, follow)
docker compose logs --tail=100 -f

# App only
docker compose logs app --tail=100 -f

# Database only
docker compose logs db --tail=50
```

Logs are emitted to stdout/stderr by each container. Docker captures and rotates them.

## Teardown

```bash
# Stop and remove containers, networks (keeps volumes)
docker compose down

# Stop and remove everything INCLUDING database volume
docker compose down -v
```

## Ports reference

| Port | Owner | Published? |
|---|---|---|
| `8010` (default) | App host port | Yes — env-overridable via `APP_PORT` |
| `8000` | App container-internal | No — compose-internal only |
| `5432` | PostgreSQL container-internal | No — compose-internal only |
| `6379` | Redis container-internal | No — compose-internal only |

Only the `app` service publishes a host port. Databases are compose-network-only.

## Troubleshooting

**App won't start — "connection refused" to db or redis**  
→ Check that `db` and `redis` services are healthy first:  
  `docker compose ps` — both should show `(healthy)`.  
  `docker compose logs db redis --tail=20`

**Healthcheck fails on the app service**  
→ The container may not have finished migrations before the healthcheck starts.  
  Try increasing `start_period` or restarting: `docker compose restart app`

**Port 8010 already in use**  
→ Set a different port: `APP_PORT=8011 docker compose up -d --build`

**Acceptance tests fail with "No events found"**  
→ The database needs seed data. The compose startup runs migrations but does not seed.  
  Run a seed script or POST events manually before running acceptance tests.

**Migrations fail on first run**  
→ Ensure the database volume is fresh: `docker compose down -v && docker compose up -d --build`
