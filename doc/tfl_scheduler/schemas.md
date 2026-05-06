# Cheat sheet: [`schemas.py`](../../src/tfl_scheduler/schemas.py)

## Big picture

Incoming HTTP JSON is unstructured (`dict`). Before touching the DB, we need **validated, normalized Python values**.

This module is the **pure validation/formatting layer** — no Flask imports, no database.

That makes it extremely easy to test and reason about: same functions could be reused from CLI or batch jobs later.

---

## Constants

### `SCHEDULE_TIME_FORMAT`

Defines the **exact textual format** the exercise specified: `%Y-%m-%dT%H:%M:%S` (no timezone field).

Parsed with **`datetime.strptime`**.

Why not timezone-aware UTC everywhere? The brief explicitly said assume **local timezone** simplicity between requester/server—so we mirrored that intentionally and would flag richer timezone handling as a future improvement.

### `VALID_LINE_IDS` (hardcoded `set`)

**Why hardcode 11 Tube line IDs here instead of querying TfL on every POST?**

1. Brief defined a finite known set — predictable validation offline.
2. Fast **fail-fast** UX for typos (`"victiral"`!) without outbound HTTP.
3. Tests remain deterministic — no mocking external metadata catalog.

**Interview upgrade path:** periodically sync from TfL’s “all lines” endpoint with caching + admin override, move list to DB/config, or tighten with official enum from shared package.

### `ValidationError`

Custom exception Flask catches centrally → **`400`** + JSON `{error: {...}}`.

---

## `extract_schedule_time(payload, *, default_to_now=...)`

Purpose: unify handling of **`schedule_time`** preferred field vs **`scheduler_time`** alias (brief typo/copy inconsistency).

### Logic breakdown

1. Read both optional keys via `.get(...)`.
2. If **both supplied and differing** → `ValidationError` — ambiguous conflicting instructions from client.
3. Pick whichever slot has a meaningful value (`schedule_time` wins if provided).
4. If missing or empty string (`""`):  
   - If `default_to_now=True`: return **current local time truncated to whole seconds**.  
     That matches requirement “empty schedule ⇒ run immediately” while keeping JSON prettier (no microseconds).
   - Else raise “required.”
5. Verify type **string**.
6. `strptime` parse or raise friendly **format mismatch** message chaining original `ValueError` (`from exc` keeps trace context developers like).

PATCH path reuses helper with **`default_to_now=True`** when PATCH includes scheduling fields — so empty reschedule string behaves like POST “immediate” semantics when present.

---

## `parse_lines(raw_lines, *, required=...)`

Input spec: **`lines`** is a comma-separated lowercase ID string (`"victoria,central"`), NOT an array (`["victoria"]`). If client sends JSON list we reject — forces single consistent wire format aligning with curls in brief.

### Steps:

1. `None`/empty string: if `required=True` ⇒ error else return `None` (PATCH omission path).
2. Non-string ⇒ error (“must be comma-separated **string**”).
3. Split on commas → strip whitespace → lowercase each token (`Victoria ` ok).
4. Skip empty leftovers from weird commas `"a,,b"`.
5. Unknown ID outside `VALID_LINE_IDS` ⇒ error embedding sorted allowed list helper text — good UX + security-ish input gate.
6. **Deduplicate** while preserving stable first-seen order via `seen` `set`.

Why dedupe?

- Avoid pointless duplicate TfL path segments `/Line/victoria,victoria/`.
- Mirrors deduped intent for analytics later.

Minimum one ID after stripping or error.

---

## `serialize_task(task)`

Flask’s `jsonify` needs plain dict/str/list/null JSON types.

We convert **`Task`** ORM object fields:

| DB / Python shape | JSON output |
|-------------------|-------------|
| `schedule_time`, timestamps | ISO strings without microseconds for calm logs |
| `lines` internally `list[str]` | **`",".join(...)` string** aligning with curls examples |

**Beginner GOTCHA:** `None` timestamps become JSON `null` via `_format_datetime`.

---

### `_format_datetime`

Internal helper stripping microseconds purely for readability & diff stability in assertions.

---

## Interview questions you can answer

**Q: Why not Pydantic?**  
Cleaner validation + automatic docs—but adds dependency footprint; pure functions suffice at this size.

**Q: Why separate module?**  
Reusable + unit-test isolation + interviewer sees architectural discipline.

---

## Stretch ideas (things you DON’T need to ship but can SAY)

Schema version field on tasks; strict JSON-schema validation of disruptions/predictions; uppercase display names normalization policy.
