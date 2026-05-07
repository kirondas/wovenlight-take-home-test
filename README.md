# TFL Scheduler Service

A small Flask service for scheduling calls to Transport for London's Line Disruption API and storing the result for later retrieval.

---

## Why the flow and repo are shaped this way

The goal is not “one big `app.py` that works,” but something that **looks like a maintainable production service**: clear boundaries, explicit configuration, and a request path you can draw on a whiteboard.

**Layers and responsibilities**

- **`app.py` (HTTP)** — Route handlers stay thin: parse JSON, call validation helpers, delegate to the repository and scheduler, turn domain outcomes into HTTP status codes. Error handlers map a small set of exception types to a consistent JSON error envelope so clients do not see raw stack traces.
- **`schemas.py` (+ `models.TaskStatus`)** — Input validation and response shaping live outside HTTP so the rules are testable and reusable. Allowed TfL line IDs and the schedule-time format are **named constants**, not stringly-typed magic scattered through routes.
- **`repository.py`** — All SQLAlchemy sessions and transactions sit here. Each public method is its own **transaction boundary** (context manager: commit / rollback / close / scoped_session cleanup). That keeps Flask and APScheduler threads from leaking session state and makes it obvious where data changes. **`expunge`** returns detached `Task` objects so callers can safely use them after the session closes—important when the scheduler or tests hold a row across boundaries.
- **`scheduler.py`** — **When** work runs is isolated from **what** the HTTP API accepts. APScheduler jobs call back into the repository and a **`DisruptionProvider`**, so scheduling policy (e.g. `date` triggers, `max(schedule_time, now)` for past times, reload pending on startup) does not clutter route code.
- **`tfl_client.py`** — Outbound HTTP is a **replaceable adapter**: a `Protocol` describes `get_disruptions`, and `TflClient` implements it with timeouts and structured errors (`ProviderTimeout`, `ProviderBadResponse`, etc.). The same task lifecycle could drive an ML endpoint later without rewriting the scheduler or repository contract.
- **`config.py` + environment** — Settings come from the environment (`AppConfig.from_env`) with sensible defaults for local dev; the `AppConfig` dataclass is **frozen** to avoid accidental mutation as it is passed through `create_app`.
- **`database.py`** — Engine and `scoped_session` construction (including SQLite `:memory:` tweaks for tests) stay in one place so deployment and tests do not duplicate connection logic.

**End-to-end flow (mental model)**

1. **Create** — Validate body → `TaskRepository.create_task` persists a **pending** row → `TaskScheduler.schedule_task` registers a **one-off** job keyed by task id.  
2. **Run** — Scheduler fires → `mark_running` (returns `None` if the task is no longer pending, so double-fires are harmless) → provider fetch → `mark_succeeded` / `mark_failed`.  
3. **Update / delete** — Mutations go through the repository; if the task is still **pending**, the scheduler is **unscheduled / rescheduled** so in-memory jobs match the database after PATCH or DELETE.

That layout is deliberate: it mirrors how you would split a real service (API vs persistence vs integration vs orchestration) and makes **trade-offs explicit** (e.g. in-process scheduler vs a queue—called out under Limitations).

---

## Code review interview: how to use this project

For a **Stage 2 technical / code review** style conversation, interviewers are usually judging whether this resembles **honest production engineering**: structure, error handling, and whether **you** can defend what is here—not whether every advanced topic is implemented.

**What to be ready to explain**

1. **Architecture** — Why these modules exist, how a request moves through them, and where you would extend behaviour (e.g. new endpoint vs new repository method vs new provider).
2. **Key design choices** — In-process **APScheduler** with `date` jobs vs external workers; **TfL** behind a **Protocol**; **repository-owned** sessions; **status** as an enum-shaped string; **Docker Compose** with a **healthcheck** so the API does not start before Postgres is ready.
3. **Trade-offs and shortcuts** — Anything simplified for time (single replica, no migrations, no retries, minimal logging) and what would break if you scaled horizontally or lost the scheduler process.
4. **Improvements with more time** — CI (lint, types, tests on every push), migrations (e.g. Alembic), a real **queue + worker** for scheduling, **idempotency** keys, retries/backoff, structured logging/metrics, auth/rate limits, stricter result schemas.

**Framing that tends to work well**

- Walk **top-down**: HTTP → validation → persistence → schedule → background run → provider.  
- Call out **one or two happy paths and one failure path** (validation 400, not found 404, conflict 409, provider failure → `failed` task).  
- Be able to go **deeper on demand** (e.g. why `scoped_session`, why `expire_on_commit=False`, why `mark_running` can return `None`). Relying on generated comments is fine for prep; in the room, you still need to **say** the reasoning in your own words.

---

## Design decisions (short list)

- Flask for a small, explicit HTTP surface.
- PostgreSQL in Docker for realistic persistence; SQLite in tests for speed.
- APScheduler in-process to keep the exercise bounded; provider behind a protocol for testability and future swaps.
- UUID task IDs; explicit task status enum.

---

## Limitations

- **Single-process scheduler** — Not safe for multiple API replicas without a distributed queue, leader election, or DB-backed locking.
- **No auth or rate limiting** — Would be required for a public service.
- **No migrations** — Tables are created with `create_all`; production would use Alembic (or similar).
- **No automatic retries** — Failed tasks stay failed; transient outages would need a retry policy.
- **Limited observability** — No structured metrics/tracing; logging is basic.
- **Loose result typing** — Success `result` is JSON from TfL, not a strict domain schema.
- **Naive datetimes** — No timezone handling; behavior follows the server clock.

---

## Time spent

**Approximately 4 hours**.

---

## Technologies and learning

- Wiring **APScheduler** `date` triggers to repository callbacks and keeping jobs in sync with CRUD.
- **TfL Line Disruption** endpoint shape and treating the client as a pluggable **provider** behind a `Protocol`.
- Compose **healthchecks** and `**depends_on: condition: service_healthy`** so the API starts after Postgres accepts connections.

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

- `**schedule_time**` — String `YYYY-MM-DDTHH:MM:SS`. If missing or empty on create/update (where applicable), the service uses **now**. Times are **naive** (server local clock). If the stored time is in the **past**, the scheduler still runs the job **as soon as possible** (`max(schedule_time, now)`), while the stored `schedule_time` field is unchanged.
- `**lines**` — Comma-separated TfL **line IDs** (not display names), e.g. `victoria,central`.

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
