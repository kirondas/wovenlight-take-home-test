# Cheat sheet: [`scheduler.py`](../../src/tfl_scheduler/scheduler.py)

## Big picture

**Problem:** someone calls `POST /tasks` with a future timestamp. Something must wake up **later** and fetch TfL disruptions.

**Chosen tool:** **APScheduler** `BackgroundScheduler` — schedules **one-off datetime jobs** (`trigger="date"`).

**Key design choice:** Scheduling is **inside the API process** → simple for a take-home, **not** distributed-safe if you horizontal-scale many replicas (each might think it should run jobs). Be ready to articulate that trade-off.

---

## Class: `TaskScheduler`

### Dependencies injected

```python
TaskRepository, DisruptionProvider
```

Dependency injection (passing collaborators into `__init__`) makes tests pass a **fake provider** with no network calls.

---

### `start()` and `shutdown()`

**`start`**

- Ensures background scheduler thread running.
- Immediately calls **`reload_pending_tasks()`**.

**Why reload on start?** After container restart, APScheduler’s in-memory job queue is empty but Postgres still has **`pending`** rows → we **rehydrate** scheduler state from DB source-of-truth.

**`shutdown`**

- Stops scheduler gracefully-ish (`wait=False`). Tests call this in fixtures to avoid dangling threads.

Interview: *“Crash/restart recovery re-registers pending rows.”*

---

### `schedule_task(task)`

```python
run_date = max(task.schedule_time, datetime.now())
```

**Edge case logic:** If user picks a time already in the past, we still run **soon** (>= now) rather than skipping — matches intuitive “run no earlier than schedule, but don’t strand historical inputs.”

```python
self._scheduler.add_job(
    self.run_task,
    trigger="date",
    run_date=run_date,
    args=[task.id],
    id=task.id,
    replace_existing=True,
)
```

**Important details:**

- **`id=task.id`**: APScheduler job id equals UUID string — easy **lookup/removal** mirrors DB key.
- **`replace_existing=True`**: idempotent re-add on restart or PATCH reschedule.

Function called is **`run_task(task_id)`**.

---

### `reschedule_task(task)`

**Unschedule** previous job then **schedule** fresh spec — prevents duplicate jobs for same UUID.

---

### `unschedule_task(task_id)`

```python
except JobLookupError:
    logger.debug(...)
```

Benign race scenarios: delete after run, double delete, etc.—**no uncaught exception propagation**.

---

### `reload_pending_tasks()`

Iterates DB `pending` rows and re-`schedule_task` each.

---

### `run_task(task_id)` — the beating heart

Steps:

1. **`mark_running`** in DB (atomic-ish attempt to leave `pending`).
2. If **`None`**: log + return — something else already moved it (delete, race).
3. **`try` provider `get_disruptions(task.lines)`**.
4. **`mark_succeeded`** with list-of-dict result.
5. Catch **`ProviderError`** (includes timeouts + bad parses if raised that way) ⇒ **`mark_failed`** textual message.
6. Catch **broad `Exception`** ⇒ still **`mark_failed`** with prefix `Unexpected provider execution error: ...`

**Why the broad `except`?**

If the provider were a Torch model wrapper, **`RuntimeError`**, **`CUDA`** issues surfaced as Python exceptions, etc.—we still want job completion state recorded **without killing background thread**.

**Lint `noqa: BLE001`:** acknowledges intentional wide catch; production might refine classification + Sentry.

**Logging:** `info` on skip, `debug` on missing job previously.

---

## Failure → user visibility

Downstream client polls **`GET /tasks/<id>`**: sees **`failed`** + **`error_message`** field—operational transparency.

---

## ML narrative mapping

| Scheduler concept | ML analogue |
|-------------------|-------------|
| `run_task` | Batch scoring step / delayed inference job |
| `mark_running` | Claim work item (compare Celery `ack` semantics) |
| `ProviderError` | Structured inference client failure |
| Broad `Exception` | Bug / unexpected stack — still captured as failed job artifact |

---

## Likely follow-up you should expect

**Q: Why not Celery/RQ?**  
Heavier operational setup (broker, workers). APScheduler matches brief simplicity.

**Q: Duplicate execution risk?**  
Two API replicas + shared DB + in-process scheduling ⇒ possible double fire **unless** distributed lock or single scheduler leader.

**Q: Exactly-once semantics?**  
We aim at **at-least-once attempt** bounded by state machine; perfect exactly-once needs idempotent downstream + dedupe keys.
