# Cheat sheet: [`models.py`](../../src/tfl_scheduler/models.py)

## Big picture

This file defines **what a “task” row looks like in the database**, using **SQLAlchemy 2.x**’s “Declarative” ORM style.

**ORM** means Object-Relational Mapping: you describe tables as Python classes; SQLAlchemy translates to SQL `CREATE TABLE`, `INSERT`, `SELECT`, etc.

## `Base` and `DeclarativeBase`

```python
class Base(DeclarativeBase):
    pass
```

All table models inherit from this `Base`. SQLAlchemy collects their metadata (table names, columns) into `Base.metadata`, which `database.py` uses to run `create_all()`.

## `TaskStatus` enum

```python
class TaskStatus(str, Enum):
```

- Inheriting **`str`** makes each member behave like a string in JSON and comparisons (`TaskStatus.PENDING == "pending"` style thinking).
- **`Enum`** gives you a fixed set of legal values: pending, running, succeeded, failed — the **workflow** of one scheduled job.

`.values()` exists so the API can validate `?status=` query parameters against the same list the DB uses.

### Why explicit status instead of a boolean “done”?

Because real jobs have more than two states:

- **pending** — not run yet (or rescheduled).
- **running** — provider call in progress (helps avoid double-run and explains “in flight”).
- **succeeded** — we have a `result`.
- **failed** — we have `error_message` instead.

## The `Task` model (table `tasks`)

Each attribute with `mapped_column` becomes a **column**.

### `id`

- Type `String(36)`: UUID text form.
- `primary_key=True`: unique row identifier.
- `default=lambda: str(uuid.uuid4())`: new row gets a random UUID when inserted.

**Interview point:** UUIDs avoid leaking sequential database IDs and are safe to expose in URLs.

### `schedule_time`

- `DateTime`, not nullable: when the job *should* run (local naive datetime per brief).

### `lines`

- Stored as **`JSON`** in Postgres/SQLAlchemy — in Python we use a **`list[str]`** (e.g. `["victoria","central"]`).
- API requests use a comma-separated string; **`schemas.parse_lines`** converts that → list before saving.

### `status`

Default `pending`. Indexed (`index=True`) because we often query “all pending tasks” on restart.

### `result` / `error_message`

- **`result`**: TfL returns a JSON **array** of disruption objects → stored as list of dicts (`JSON` column). `NULL`/`None` when not finished or failed paths clear it.
- **`error_message`**: human-readable explanation when `failed`; `Text` allows long messages vs a short `VARCHAR`.

### Timestamps

- **`created_at`**: set when row is inserted.
- **`updated_at`**: updated on modifications (`onupdate=datetime.now`).
- **`executed_at`**: set when a run completes (success or failure) — **business** time vs `updated_at` (any column change).

**Subtle beginner note:** `default=datetime.now` passes the function; SQLAlchemy calls it per insert. Similarly `lambda` for UUID runs per insert.

## What to say when they ask “ML angle”

Same table could store **`result`** as model predictions (`list[dict]`) instead of disruptions; **`error_message`** catches inference timeouts, bad JSON schemas, CUDA OOM wrappers, etc.

## Common interview questions

**Q: Why not raw SQL in the codebase?**  
We use SQLAlchemy for portability (Postgres in Docker, SQLite in tests) and to keep Python types close to columns.

**Q: Where do migrations fit?**  
`create_all()` is fine for a demo. Production uses **Alembic** migrations so you never surprise-drop prod data.

**Q: Timezones?**  
Brief said assume local wall time; we did not introduce `timezone-aware` datetimes — you can flag that as a known simplification.
