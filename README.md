# TFL Scheduler Service

A small Flask service for scheduling calls to Transport for London's Line
Disruption API and storing the result for later retrieval.

The service is intentionally simple, but it is structured like a small
production codebase: the API layer validates requests, the repository owns
database access, the scheduler decides when work runs, and the provider client
contains the external TFL call. The TFL client is treated as a replaceable
provider, so it could later be swapped for an ML inference call with the same
task lifecycle.

## Tech Stack

- Python 3.10+
- Flask
- SQLAlchemy
- APScheduler
- PostgreSQL
- Docker Compose
- pytest

## Run With Docker

```bash
docker compose up --build
```

The API will be available at:

```text
http://localhost:5555
```

Docker Compose starts two containers:

- `api`: the Flask service and in-process scheduler.
- `db`: PostgreSQL for task state and results.

## Run Tests

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the test suite:

```bash
python -m pytest
```

The tests use SQLite in memory for speed and mock the TFL provider so they do
not depend on the live TFL API.

## API

### Health Check

```bash
curl http://localhost:5555/health
```

Response:

```json
{"status": "ok"}
```

### Create A Task

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"schedule_time":"2099-01-01T17:00:00","lines":"victoria,central"}' \
  http://localhost:5555/tasks
```

JSON field **`schedule_time`** uses local wall time in the form
`%Y-%m-%dT%H:%M:%S` (see task brief).

If `schedule_time` is empty or missing, the task is scheduled to run
immediately:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"lines":"victoria"}' \
  http://localhost:5555/tasks
```

### List Tasks

```bash
curl http://localhost:5555/tasks
```

Optional status filter:

```bash
curl http://localhost:5555/tasks?status=pending
```

Valid statuses are `pending`, `running`, `succeeded`, and `failed`.

### Get One Task

```bash
curl http://localhost:5555/tasks/<task_id>
```

Completed tasks include `result`. Failed tasks include `error_message`.

### Update A Pending Task

```bash
curl -X PATCH \
  -H "Content-Type: application/json" \
  -d '{"schedule_time":"2099-01-01T18:30:00","lines":"jubilee"}' \
  http://localhost:5555/tasks/<task_id>
```

Only `pending` tasks can be updated. Once a task is `running`, `succeeded`, or
`failed`, the service returns `409 Conflict`.

### Delete A Task

```bash
curl -X DELETE http://localhost:5555/tasks/<task_id>
```

Pending tasks are also removed from APScheduler. Running tasks cannot be
deleted and return `409 Conflict`.

## Valid Line IDs

The service accepts TFL Tube line IDs, not display names:

```text
bakerloo, central, circle, district, hammersmith-city, jubilee,
metropolitan, northern, piccadilly, victoria, waterloo-city
```

## Error Handling

The API returns clear JSON errors for invalid input, missing tasks, and invalid
task state transitions.

Scheduled task failures are stored on the task record instead of crashing the
service. This includes:

- TFL/provider timeouts.
- TFL/provider HTTP failures.
- Invalid or malformed provider responses.
- Unexpected runtime exceptions.

This is similar to how I would handle a scheduled ML model call. If TFL were
replaced by model inference, the same lifecycle could record model loading
errors, inference timeouts, invalid prediction payloads, or unexpected runtime
failures.

## Design Decisions

- Flask was chosen because it is simple, explicit, and suggested in the task.
- PostgreSQL was chosen over SQLite to demonstrate realistic persistence and a
  multi-container Docker setup.
- APScheduler is used in-process to keep the exercise understandable within a
  few hours.
- UUIDs are used for task IDs so clients do not depend on database row numbers.
- Task status is explicit: `pending`, `running`, `succeeded`, or `failed`.
- The provider client is isolated so the external call can be replaced without
  rewriting the API or repository layers.

## Limitations And Improvements

- The scheduler runs inside the Flask process. In a multi-replica deployment,
  this could cause duplicate execution unless replaced with a distributed
  scheduler, queue, or database locking strategy.
- There is no authentication or rate limiting. A production service should add
  both.
- Database migrations are not included. For production, I would add Alembic.
- Failed tasks are not retried automatically. A production version could add
  retry policy for transient provider failures.
- Observability is minimal. I would add structured logs, metrics, and alerts
  for failed task execution.
- The service stores raw TFL responses. For production, I would define a stricter
  result schema and possibly store normalized disruption records.

## Time Spent

Approximately 3-4 hours.

I used Flask, SQLAlchemy, APScheduler, Docker Compose, and pytest. I had used
the general patterns before, but checked the exact task requirements carefully
while building the service.
