# WovenLight TfL Scheduler

A small Flask service for scheduling calls to the Transport for London Line Disruption API and storing the results.

The implementation is intentionally modest: Flask for the REST API, APScheduler for in-process scheduling, **PostgreSQL** for persistence, and Docker Compose for repeatable local execution. The goal is to show production-minded structure without hiding the core behaviour behind too much infrastructure.

## Architecture

```mermaid
flowchart LR
    Client[cURL or API client] --> FlaskAPI[Flask API]
    FlaskAPI --> TaskService[Task service]
    TaskService --> Repository[Task store]
    TaskService --> Scheduler[APScheduler]
    Scheduler --> TflClient[TfL Line API client]
    TflClient --> TflAPI[TfL API]
    Scheduler --> Repository
    Repository --> Db[(PostgreSQL)]
```

Key modules:

- `wovenlight_scheduler.api`: HTTP routes and error translation.
- `wovenlight_scheduler.service`: task orchestration rules.
- `wovenlight_scheduler.repository`: PostgreSQL persistence (`DATABASE_URL`).
- `wovenlight_scheduler.scheduler`: APScheduler integration and task execution.
- `wovenlight_scheduler.tfl_client`: TfL API client with timeout/error handling.
- `wovenlight_scheduler.domain`: task models, statuses, datetime parsing, and line validation.

## Run With Docker

Docker Compose starts **two** containers:

- **`db`**: PostgreSQL 16 (task data in the `pgdata` volume; port **5432** published to the host).
- **`api`**: this service, configured with `DATABASE_URL` pointing at `db`.

```bash
docker compose up --build
```

The API listens on `http://localhost:5555`. Wait until the `db` service passes its health check before creating tasks (Compose `depends_on` handles this for `api`).

Inspect the database from the host:

```bash
docker compose exec db psql -U scheduler -d scheduler -c "SELECT id, status, lines FROM tasks;"
```

## Run Locally (without Compose)

You need a reachable PostgreSQL instance and **`DATABASE_URL`**. With Compose’s `db` running and port 5432 exposed:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
export DATABASE_URL=postgresql://scheduler:scheduler@localhost:5432/scheduler
python -m wovenlight_scheduler
```

On Windows PowerShell:

```powershell
$env:DATABASE_URL = "postgresql://scheduler:scheduler@localhost:5432/scheduler"
python -m wovenlight_scheduler
```

If `DATABASE_URL` is missing, the process exits with a short error message.

Useful environment variables:

- **`DATABASE_URL`** (required): e.g. `postgresql://user:pass@host:5432/dbname`.
- **`PORT`**: API port, default `5555`.
- **`TFL_BASE_URL`**: TfL base URL, default `https://api.tfl.gov.uk`.
- **`REQUEST_TIMEOUT_SECONDS`**: outbound HTTP timeout, default `5`.

## API

Schedule a task:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"schedule_time":"2026-05-06T17:00:00","lines":"victoria,central"}' \
  http://localhost:5555/tasks
```

The task sheet uses `scheduler_time` in a few examples. This service accepts that alias too, but documents `schedule_time` as the canonical field.

Create a task to run immediately:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"schedule_time":"","lines":"victoria"}' \
  http://localhost:5555/tasks
```

List tasks:

```bash
curl http://localhost:5555/tasks
```

Get one task:

```bash
curl http://localhost:5555/tasks/<task_id>
```

Update a pending task:

```bash
curl -X PATCH \
  -H "Content-Type: application/json" \
  -d '{"schedule_time":"2026-05-06T18:00:00","lines":"jubilee"}' \
  http://localhost:5555/tasks/<task_id>
```

Delete a task:

```bash
curl -X DELETE http://localhost:5555/tasks/<task_id>
```

Deleting a pending task cancels the scheduled APScheduler job and marks the stored task as `cancelled`.

## Task Lifecycle

Tasks move through these statuses:

- `pending`: stored and waiting for its scheduled time.
- `running`: currently executing the TfL call.
- `completed`: TfL response stored in `result`.
- `failed`: execution failed and the error is stored in `error`.
- `cancelled`: task was deleted through the API.

Only `pending` tasks can be updated. This avoids ambiguous behaviour once a task has already started or produced a result.

## Supported Line IDs

The service validates against the 11 London Underground line IDs:

`bakerloo`, `central`, `circle`, `district`, `hammersmith-city`, `jubilee`, `metropolitan`, `northern`, `piccadilly`, `victoria`, `waterloo-city`.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

By default, tests start a **throwaway PostgreSQL** via [Testcontainers](https://testcontainers.com/) (requires **Docker** running). TfL is mocked; no outbound TfL calls in tests.

To use your own Postgres instead (e.g. CI service container):

```bash
export TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/testdb
pytest
```

## Design Trade-Offs

- Schema is created with `CREATE TABLE IF NOT EXISTS` on startup; there is no migration framework yet.
- APScheduler runs in the API process. This is simple and transparent, but multiple API replicas could execute the same task unless scheduling is moved to a separate worker or guarded by database locks.
- The service assumes local naive datetimes because the exercise explicitly says UTC/timezone handling is not required. A production API should store UTC and validate timezone-aware inputs.
- There is no authentication, rate limiting, or request tracing. Those would be added before exposing the service beyond a trusted environment.
- TfL failures are recorded on the task as `failed`; retries/backoff would be a natural next step.

## Production Improvements

Given more time, I would add:

- Alembic (or similar) migrations instead of relying on `CREATE TABLE IF NOT EXISTS`.
- A separate worker process backed by a queue such as Celery/RQ or a workflow orchestrator.
- Idempotency keys for task creation.
- Structured JSON logging and correlation IDs.
- CI running tests and Docker build checks on every pull request.
- OpenAPI documentation generated from request/response schemas.

## Time Spent

Approximately 4 hours. Stack: Flask, pytest, Docker, PostgreSQL, and APScheduler.
