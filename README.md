# TFL Scheduler Service

A small Flask service for scheduling calls to Transport for London's Line Disruption API and storing the result for later retrieval.

The service is intentionally simple. However, it is structured like a small production codebase, where:

- The API layer validates requests
- The repository owns database access
- The scheduler decides when work runs
- The provider client contains the external TFL call

The TFL client is treated as a replaceable provider, so it could later be swapped for an ML inference call with the same task lifecycle.

---

## How to run the server (Docker)

```bash
docker compose up --build
```

---

## How to run tests (Windows)

From the **project root** in **Command Prompt**:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt .
python -m pytest
```

---

## API overview


| Method   | Path               | Description                                                                               |
| -------- | ------------------ | ----------------------------------------------------------------------------------------- |
| `GET`    | `/health`          | Liveness: `{"status":"ok"}`.                                                              |
| `POST`   | `/tasks`           | Create a task. Body: `lines` (required), `schedule_time` (optional). **201** + task JSON. |
| `GET`    | `/tasks`           | List tasks. Query: optional `status` (`pending`, `running`, `succeeded`, `failed`).       |
| `GET`    | `/tasks/<task_id>` | Get one task. **404** if missing.                                                         |
| `PATCH`  | `/tasks/<task_id>` | Update **pending** task only (`schedule_time` and/or `lines`). **409** if not pending.    |
| `DELETE` | `/tasks/<task_id>` | Delete task. **409** if **running**. **204** on success.                                  |


### Task JSON shape

Each task is returned as a JSON object with:

- `**id`** — UUID string.
- `**schedule_time`** — ISO-like string (no timezone; wall clock as stored).
- `**lines`** — comma-separated line IDs (see below).
- `**status`** — `pending`, `running`, `succeeded`, or `failed`.
- `**result**` — TfL-shaped list of disruption objects, or `null` until success.
- `**error_message**` — string on failure, else `null`.
- `**created_at**`, `**updated_at**`, `**executed_at**` — timestamps or `null`.

### Request fields

- `**schedule_time**` — String `YYYY-MM-DDTHH:MM:SS`. If missing or empty on
create/update (where applicable), the service uses **now**. Times are **naive**
(server local clock). If the stored time is in the **past**, the scheduler
still runs the job **as soon as possible** (`max(schedule_time, now)`), while
the stored `schedule_time` field is unchanged.
- `**lines`** — Comma-separated TfL **line IDs** (not display names), e.g.
`victoria,central`.

---

## Example calls

**Health**

```bash
curl http://localhost:5555/health
```

**Create a task for a single line**

```bash
curl -s -X POST http://localhost:5555/tasks -H "Content-Type: application/json" -d "{\"schedule_time\":\"2050-01-01T17:00:00\",\"lines\":\"central\"}"
```

**Create a task multiple lines**

```bash
curl -s -X POST http://localhost:5555/tasks -H "Content-Type: application/json" -d "{\"schedule_time\":\"2099-01-01T17:00:00\",\"lines\":\"victoria,central\"}"
```

**Create with immediate default time**:

```bash
curl -s -X POST http://localhost:5555/tasks -H "Content-Type: application/json" -d "{\"lines\":\"central\"}"
```

**List tasks:**

```bash
curl http://localhost:5555/tasks
```

**List pending tasks:**

```bash
curl http://localhost:5555/tasks?status=pending
```

**Get task**

```bash
curl -s http://localhost:5555/tasks/TASKID
```

**Update task**

```bash
curl -X PATCH -H "Content-Type: application/json" -d "{\"schedule_time\":\"2099-01-01T18:30:00\",\"lines\":\"jubilee\"}" http://localhost:5555/tasks/TASKID
```

**Delete task**

```bash
curl -X DELETE http://localhost:5555/tasks/TASKID
```

### Valid line IDs

```text
bakerloo, central, circle, district, hammersmith-city, jubilee,
metropolitan, northern, piccadilly, victoria, waterloo-city
```

### Error handling

Validation and bad input → **400** with `validation_error`. Missing task or
route → **404**. Wrong task state (e.g. patch non-pending, delete while
running) → **409** with codes such as `task_not_pending`, `task_running`.

Scheduled work that fails (TfL timeout, HTTP error, bad JSON, unexpected
errors) is recorded on the task (`failed` + `error_message`) without crashing
the process.

---

## Tech stack

- Python 3.10+
- Flask, SQLAlchemy, APScheduler, PostgreSQL, Docker Compose, pytest

---

## Design decisions (short)

- Flask for a small, explicit HTTP surface.
- PostgreSQL in Docker for realistic persistence; SQLite in tests for speed.
- APScheduler in-process to keep the exercise bounded; provider behind a
protocol for testability and future swaps.
- UUID task IDs; explicit task status enum.

---

## Limitations

- **Single-process scheduler** — Not safe for multiple API replicas without a
distributed queue, leader election, or DB-backed locking.
- **No auth or rate limiting** — Would be required for a public service.
- **No migrations** — Tables are created with `create_all`; production would use
Alembic (or similar).
- **No automatic retries** — Failed tasks stay failed; transient outages would
need a retry policy.
- **Limited observability** — No structured metrics/tracing; logging is basic.
- **Loose result typing** — Success `result` is JSON from TfL, not a strict
domain schema.
- **Naive datetimes** — No timezone handling; behavior follows the server clock.

---

## Time spent

**Approximately 4 hours** end-to-end (implementation, Docker, tests, and README).
Adjust this line if your own tally differs.

---

## Technologies and learning

**Already familiar:** Python, Flask, SQLAlchemy, pytest, Docker Compose, REST
APIs.

**Learned or refreshed while doing this exercise:** (edit to match your
experience — examples below)

- Wiring **APScheduler** `date` triggers to repository callbacks and keeping
jobs in sync with CRUD.
- **TfL Line Disruption** endpoint shape and treating the client as a pluggable
**provider** behind a `Protocol`.
- Compose **healthchecks** and `**depends_on: condition: service_healthy`** so
the API starts after Postgres accepts connections.

If you had not used one of the above before, say so honestly in one sentence
per item.