# Cheat sheet: [`repository.py`](../../src/tfl_scheduler/repository.py)

## Big picture — “Repository pattern”

The **repository** is a dedicated object that contains **all database access** for `Task`s.

Why not put SQL/query logic inside Flask route functions?

| Benefit | Explanation |
|---------|--------------|
| **Separation of concerns** | Routes talk HTTP + validation; persistence is one layer down |
| **Testability** | You can swap the repo with a fake, or reuse it from a CLI job |
| **Consistency** | Commits rollbacks handled one way everywhere |

Think of **`TaskRepository` as “the database API for tasks.”**

---

## Session lifecycle (`_session` context manager)

Every public repository method wraps work like this:

```python
@contextmanager
def _session(self) -> Iterator:
    session = self._session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        if hasattr(self._session_factory, "remove"):
            self._session_factory.remove()
```

Translate to beginner language:

1. Borrow a Session from the pool / scoped registry.
2. Do work (`yield`).
3. If nothing blew up → **`commit()`** (make changes permanent).
4. If exception → **`rollback()`** (discard partial writes), re-raise.
5. **`close()`** and **`remove()`** clean up scoped sessions on this thread/greenlet.

**Interview phrase:** **“transactions are bounded per repository operation.”**

---

## Why `flush()` then `expunge()` after creating / loading?

Rough pattern:

```python
session.flush()
session.expunge(task)
```

- **`flush`** sends pending SQL (`INSERT`) so databases can assign/autogenerate IDs and defaults consistently before we read them in Python on the instance.
- **`expunge`** detaches the Python object from the Session so using it later does not trigger lazy loads against a Session that might be closed — important after `commit()` / `close()`.

Trade-off acknowledged: detach patterns can feel heavy; simpler apps sometimes return serialized dicts earlier.

---

## Method-by-method

### `create_task`

Builds ORM instance, adds to session, flush, detach, returns `Task`.

### `get_task`

`session.get(Task, task_id)` — primary-key lookup efficient in SQL → `Optional[Task]` if missing.

### `list_tasks(status=...)`

`select(Task)...` with optional `WHERE status = …`, ordered by `created_at`.

### `update_pending_task`

Only allows updates if task exists **and status is pending** matching business rules enforced again at route level for HTTP status codes.

Clears **`result`** and **`error_message`** when editing a pending row so stale success/failure blobs do not linger after reschedule.

Raises **`TaskNotFoundError`** or **`TaskStateError`** mapped to Flask error handlers → consistent JSON envelope.

### `delete_task`

Removes row; raises **`TaskNotFoundError`** when missing — route often checks first anyway, but concurrent deletes could bubble here safely.

### `mark_running`

Try to transition **`pending → running`**.

Returns **`None`** if impossible (already ran, deleted, etc.). **Scheduler relies on `None`** to skip duplicate/stale executions.

### `mark_succeeded`

Sets status, attaches `result` JSON-like list-of-dicts, timestamps `executed_at`.

### `mark_failed`

Sets status failed, clears `result`, fills `error_message`, timestamps `executed_at`.

`_get_existing` centralizes **`TaskNotFoundError`** raising for mutate-after-success pathways.

---

## Custom exceptions (`TaskNotFoundError`, `TaskStateError`)

They are deliberately **narrow** exceptions so Flask can register:

```python
@app.errorhandler(TaskNotFoundError)
```

Returning JSON like `404` / `409` instead of Flask’s generic HTML trace pages.

Routes also sometimes return **`404`** directly when `get_task` returns None — both patterns exist intentionally (route-level vs repository-level edge cases depending on concurrency and call site).

---

## ML / scheduler tie-in

`mark_failed` textual errors can hold:

- Inference timeout message
- “Invalid prediction schema …”  
Same repository methods work if provider is **`TflClient`** or **`ModelClient`**.

---

## What improvement would you name?

Distributed locking / **SELECT FOR SKIP LOCKED** if multiple workers drained the same pending queue — acknowledged limitation of in-process scheduler.
