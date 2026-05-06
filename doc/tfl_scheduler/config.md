# Cheat sheet: [`config.py`](../../src/tfl_scheduler/config.py)

## Big picture

This module holds **configuration**: where the database is, what TfL URL to use, how long HTTP calls may take, whether the scheduler should start, and whether we are in testing mode.

Keeping config in one module means **routes and database code do not hardcode magic strings** scattered everywhere.

## Key idea: environment variables

Production services almost never bake secrets or hostnames into source code. Instead, the process reads **environment variables** at startup (Docker, Kubernetes, systemd, etc. set them).

`AppConfig.from_env()` is a **factory method** that reads `os.getenv(...)`, converts types, and builds an `AppConfig` object.

## Dataclass and `frozen=True`

```python
@dataclass(frozen=True)
class AppConfig:
```

- A **dataclass** is a shorthand for “a class that mostly holds data fields.” Python auto-generates `__init__`, `__repr__`, comparisons, etc.
- `frozen=True` means: **after creation, you cannot mutate** the object (`config.database_url = "..."` would error). That reduces bugs: config is read-only for the app’s lifetime.

## Each field in plain English

| Field | Meaning | Default / env |
|-------|---------|----------------|
| `database_url` | SQLAlchemy connection URL (Postgres or SQLite) | `DATABASE_URL` or local Postgres default |
| `tfl_base_url` | Root URL for TfL API | `TFL_BASE_URL` or `https://api.tfl.gov.uk` |
| `request_timeout_seconds` | Max seconds for a single TfL HTTP request | `REQUEST_TIMEOUT_SECONDS` or `10` |
| `start_scheduler` | Whether APScheduler threads start with the app | `START_SCHEDULER`; any value other than `"false"` enables |
| `testing` | Passed into Flask’s `TESTING` config | `FLASK_TESTING` → `true`/`false` |

## Type conversions

Environment variables are **always strings**. Notice:

```python
request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10")),
```

If someone sets `REQUEST_TIMEOUT_SECONDS=not_a_number`, the app will **crash at startup** when building config. In a larger system you would validate and print a friendly error. For a take-home it is acceptable to mention that trade-off.

Boolean parsing is done manually:

```python
start_scheduler=os.getenv("START_SCHEDULER", "true").lower() != "false"
```

So `"True"`, `"TRUE"`, `"yes"` all keep the scheduler on — only explicit `"false"` turns it off.

## Why defaults include a Postgres URL

Without Docker, developers might run Postgres on `localhost`. The default DSN matches a typical local username/password/db from `docker-compose.yml` so `create_app()` works with minimal setup.

## Interview talking points

1. **12-factor style:** config in the environment, not in the repo.
2. **Immutable config object:** avoids accidental mutation mid-request.
3. **Test hook:** `testing=True` + `start_scheduler=False` (set in tests via `AppConfig(...)`) avoids background threads during pytest.

## If they ask “what would you add?”

- **Pydantic Settings** or similar for validation and typed env loading.
- Separate **secrets** from non-secrets (Vault, AWS Secrets Manager).
- **Per-environment** config profiles (dev/stage/prod) without copying code.
