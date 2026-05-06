# Cheat sheet: [`database.py`](../../src/tfl_scheduler/database.py)

## Big picture

This module bridges **two concerns**:

1. Create a SQLAlchemy **Engine** (connection pool + dialect for Postgres vs SQLite).
2. Create a **session factory** so repository code can open short-lived “units of work.”

It also runs **`create_all()`** which creates tables if they don’t exist (based on models inheriting `Base`).

---

## SQLAlchemy pieces (beginner mental model)

- **Engine** — knows how to talk to Postgres or SQLite (connection string parsing, pooling).
- **Session** — a workspace: you attach objects, query, commit or rollback changes.
- **Session factory / `sessionmaker`** — a callable `session_factory()` that creates new sessions sharing the same engine config.

---

## `build_session_factory(database_url: str)`

### Engine keyword arguments

```python
engine_kwargs = {"future": True, "pool_pre_ping": True}
```

- **`future=True`**: opts into SQLAlchemy 2.0 behaviors consistently (“2.0 style” APIs).
- **`pool_pre_ping`**: before handing out a pooled connection, ping it; if stale, recycle. Helps when DB restarts or network blips idle connections.

---

## Special case: `sqlite:///:memory:` (used in pytest)

SQLite in-memory is **not shared like a normal file DB** unless you reuse the same connection. Tests want a **fresh, fast DB** per test run without Docker.

Problems with default SQLite + threading:

- SQLite restricts sharing connections across threads by default (`check_same_thread`).
- An in-memory DB can “disappear” between connections unless you pin the pool.

So we configure:

```python
engine_kwargs["connect_args"] = {"check_same_thread": False}
engine_kwargs["poolclass"] = StaticPool
```

### What `StaticPool` does here

Roughly: **keep one underlying connection** for the whole pool so `:memory:` stays alive across ORM usage in the Flask test app thread.

---

## Tables: `Base.metadata.create_all(engine)`

Important nuance:

- **Demo / take-home**: auto-create tables is convenient.
- **Production**: teams use **Alembic** migrations instead, so schema changes are versioned and reviewed.

You should be ready to say: *“I used `create_all` for speed; I’d swap to Alembic for real deployment.”*

---

## `scoped_session` + `sessionmaker`

```python
session_factory = scoped_session(
    sessionmaker(bind=engine, expire_on_commit=False, future=True)
)
```

### `sessionmaker`

Builds a **template** for sessions bound to this engine.

### `expire_on_commit=False`

Normally after `commit()`, ORM instances may **expire**, so touching lazy-loaded fields later triggers DB queries.

We set **`False`** so objects returned from the repository remain readable after commit without refresh — convenient for Flask responses and tests after `expunge`-style patterns.

### `scoped_session`

Ties sessions to something like **the current greenlet/thread**. In Flask’s traditional model (request per thread), that often means **one session per request thread**, which simplifies “where is my Session?” debates.

Small note: **`scoped_session` has `remove()`** — repository code tries to call it on the factory after `close()`, which matches SQLAlchemy’s guidance for freeing thread-local state.

---

## What to say in interview

> “This module hides engine creation and SQLite vs Postgres quirks. Repository code only sees `session_factory()`. Tables are bootstrapped with `create_all` for simplicity; migrations would replace that in production.”
