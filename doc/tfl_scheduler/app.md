# Cheat sheet: [`app.py`](../../src/tfl_scheduler/app.py)

## Big picture

This is the **Flask HTTP application**: URL routes → validate JSON → repository + scheduler orchestration → JSON responses.

It uses the **application factory** pattern **`create_app()`** instead of a global `app` created at import time.

### Why factories matter (say this calmly)

Tests (and Docker) want **different config** — database URL, disable background scheduler threads, fake TfL client — without patching globals.

Calling `create_app(...)` produces a fresh **`Flask` instance** wired each time.

---

## `create_app(config=None, provider=None)`

### Steps in order:

1. Load **`AppConfig.from_env()`** unless `config` injected (tests supply explicit object).
2. `app = Flask(__name__)` — standard Flask kernel.
3. `app.config["TESTING"]` mirrors config flag (Flask uses this subtly for exceptions behavior).
4. **`build_session_factory`** → `(session_factory, engine)`.
5. Instantiate **`TaskRepository(session_factory)`**.
6. Instantiate provider: **`provider or TflClient(...)`**. Tests bypass real HTTP by passing **`FakeProvider`**.
7. **`TaskScheduler(repository, provider)`**.
8. Stash big components on **`app.extensions[...]`** — conventional Flask pattern for teardown hooks/tests retrieving pieces without module-level globals.
9. Possibly **`task_scheduler.start()`** — skipped in tests (`start_scheduler=False`) to silence background concurrency noise.
10. **`register_routes(...)`**, **`register_error_handlers(...)`**, return **`app`**.

**Interview takeaway:** Dependencies flow **into** the factory, not hidden globals.

---

## `register_routes`

### `/health` GET

Simple `{"status": "ok"}` — container orchestrators/readiness probing baseline.

Cheap note: readiness might later include DB ping; liveness stays trivial.

---

### `POST /tasks`

1. `_json_payload()` ensures JSON **object**.
2. `extract_schedule_time(..., default_to_now=True)` — empty ⇒ immediate-ish schedule per brief.
3. `parse_lines(..., required=True)`.
4. `repository.create_task(...)`.
5. `task_scheduler.schedule_task(task)` wires APScheduler hook.
6. Return **`201 Created`** serialized task JSON.

Ordering matters: persistence first ⇒ stable UUID existed before scheduler references id.

---

### `GET /tasks`

Optional **`?status=`** filter validated against **`TaskStatus.values()`** (`Enum` textual values). Invalid filter raises **`ValidationError`** → **`400`** error handler uniformity.

Otherwise list JSON array of serialized tasks ascending created time implicitly via repository ordering.

---

### `GET /tasks/<task_id>`

Lookup; missing → **`404`** JSON envelope via `_error` helper (not throwing `TaskNotFoundError` route-level shortcut — still consistent shape).

Hitting existing row returns **`200`** + serialized snapshot.

Potential improvement you can mention verbally: validating UUID formatting pre-lookup to differentiate **`400 malformed`** vs **`404 missing`**.

---

### `PATCH /tasks/<task_id>` (only pending edits)

Stages:

1. Fetch existing or **`404`**.
2. Ensure **`status == pending`**, else **`409 Conflict`** semantics (`task_not_pending`).

Why block edits after pending? Requirement + prevents mutating immutable historical executions.

Payload rules:

Detect presence keys:

```python
has_schedule_time = "schedule_time" in payload
has_lines = "lines" in payload
```

Ensures PATCH cannot be empty `{}` accidentally — avoids silent no-op puzzlement.

Rebuild partial updates:

- If **`schedule_time` was in the body** — re-parse with `default_to_now=True` (empty string ⇒ run now).
- If lines existed — optional parse — else untouched.

Calls **`update_pending_task`**, clears stale results via repository internals, **`reschedule_task()`** rewriting APScheduler binding.

Returns **`200`**.

Nuanced interview footnote distinguishing **`null` vs absent key`** — Flask JSON may include explicit null semantics; `.get("lines")` returns `None` but presence check distinguishes omitted vs included.

---

### `DELETE /tasks/<task_id>`

Flow:

| Case | Handling |
|------|----------|
| Missing | **`404`** |
| `running` | **`409`** (avoid inconsistent mid-flight deletion semantics) |
| `pending` | `unschedule_task` then DB delete row |
| `succeeded` / `failed` | Straight delete archival row semantics |

Returns **`204 No Content`** empty body signaling success devoid of redundant JSON.

---

## `register_error_handlers`

Central mapping:

| Exception / code | Response |
|------------------|---------|
| `ValidationError` | `400 validation_error` |
| bare `404` routes | generic route not found JSON (`not_found`) |
| `TaskNotFoundError` | `404` task variant |
| `TaskStateError` | `409` variant |

Uniform JSON envelope **`{"error":{"code","message"}}`**.

Consistency helps mobile/web clients programmatically branch.

---

### `_json_payload()`

Uses `silent=True` to avoid Flask raising on parse errors — we escalate controlled **`ValidationError`** if payload not dict-shaped (including non-JSON POST bodies).

---

### `_error(...)`

Thin wrapper emitting JSON + numeric HTTP status enums from **`http.HTTPStatus`** readability perk.

---

## `if __name__ == "__main__"`

Running module directly (`python -m tfl_scheduler.app`) binds dev server **`127.0.0.1:5555`** unless env overrides **`FLASK_HOST` / `FLASK_PORT`**.

Production realistically uses **`gunicorn` / `uwsgi`** — mention that distinction.

---

## Mental map for interviewer whiteboard arrows

Browser/curl ⇄ Flask `app`: routes  
Routes ⇄ **`schemas`** validation  
Routes ⇄ **`TaskRepository`** DB  
Routes ⇄ **`TaskScheduler`** background jobs  
`TaskScheduler.run_task` ⇄ **`DisruptionProvider` / `TflClient`** outbound HTTP

Keep that loop in mind and you'll narrate crisply even if nervous.

---

## Extensions you can verbally volunteer

JWT auth middleware, **`MAX_CONTENT_LENGTH`**, Prometheus metrics counter on task terminal states, OpenAPI swagger generation scanning route docstrings elsewhere.
