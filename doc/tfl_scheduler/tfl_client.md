# Cheat sheet: [`tfl_client.py`](../../src/tfl_scheduler/tfl_client.py)

## Big picture

This module hides **everything about talking to TfL’s HTTP JSON API** behind a tiny surface area.

Architectural idea (great for ML interviews):

> **`TflClient` is interchangeable with anything that exposes `get_disruptions(lines)`.**  
> In production ML, that might POST features to TorchServe/SageMaker/Vertex instead of TfL—but your scheduler + DB code would barely change.

That is why **`DisruptionProvider` is typed as a `Protocol`**.

---

## `Protocol` (structural typing) — intuition

Typically you subclass an ABC interface. **`typing.Protocol`** says:

> Any object implementing the right methods with the **right signatures** “counts,” even without inheritance.

Advantages:

- Tests inject **simple fake objects** (“duck typing”).
- Keeps **`TaskScheduler`** decoupled from concrete HTTP library details.

Interview line:

> “The scheduler depends on a capability (`get_disruptions`), not an implementation (`TflClient`).”

---

## Exception hierarchy

```
ProviderError
 ├── ProviderTimeout
 └── ProviderBadResponse
```

### Design intent

Separate **network/time** failures from **semantic/parsing/shape** problems:

| Class | Typical causes |
|-------|----------------|
| `ProviderTimeout` | Request exceeded `requests` timeout — hung network or slow TfL endpoint |
| `ProviderError` (base) | Broader **`requests`** failures: DNS, TLS, generic HTTPError after handshake, connectivity offline |
| `ProviderBadResponse` | Non-JSON text, invalid JSON decoding, unexpected JSON topology |

**Interview tie-in (“ML path”):** Map **timeout** ↔ GPU cold-start / overloaded inference autoscaler; **`ProviderBadResponse`** ↔ malformed JSON enveloping predictions or wrong schema version.

Scheduler catches **`ProviderError`** (inherits timeout + generic) distinctly from unknown **`Exception`**—see **`scheduler.py`**.

---

## `TflClient.__init__`

Stores:

- Stripped **`base_url`** (no accidental `//`).
- **`timeout`** bound into `requests.get`.

Why timeout matters? Infinite blocking threads risk **blocking worker pools** forever.

---

## `get_disruptions(lines: list[str]) -> list[dict]`

### Build URL matching TfL spec

Comma-join lowercase IDs validated upstream:

`/Line/{bakerloo,jubilee,...}/Disruption`

### Phase 1: HTTP + status

Wrapped in **`try`**:

```python
response.raise_for_status()
```

That turns **HTTP 4xx/5xx** into **`HTTPError`** (subclass of `RequestException`).

Separate **`requests.Timeout`** first so we elevate to **`ProviderTimeout`** with tighter operator messaging clarity.

Everything else under requests failures becomes **`ProviderError`** with message containing original context.

### Phase 2: JSON parse

`response.json()` ultimately decodes bytes to Python objects; failure becomes **`ValueError`** → **`ProviderBadResponse`**.

### Phase 3: minimal schema validation

Guarantees:

1. Top-level **list** (TfL returns JSON array of disruption objects).  
2. Each element is a **dict** (`object` in JSON terms).

If not → **`ProviderBadResponse`**.

**Why still minimal?** Full field-level schema (pydantic models) is optional weight for take-home; we still prevent catastrophic misinterpretation (dict root, string list, etc.).

### Empty list `[]`

This is **success with zero disruptions** — not an error.

---

## What is **not** implemented (fair limitations to mention)

| Gap | Why mention it |
|-----|----------------|
| No retries / backoff | Transient 503 might succeed on retry — easy story for extension |
| No separate connect vs read timeout split | Finer control in flakey networks |
| No max body size guard | Protect against misbehaving giant JSON |
| No rate-limit / 429 handling | TfL may throttle heavy usage |
| No circuit breaker | Stop hammering dead dependency |

---

## Quick interview flow walk

1. Scheduler thread calls client.
2. Client normalizes failure modes into typed exceptions.
3. Scheduler converts them into persisted **`failed`** tasks with human-readable error text (see repository + scheduler docs).

---

## One clean closing statement

> “This client is my **provider boundary**: network concerns and response validation stay here so the rest of the service models **job lifecycle**, not HTTP edge cases.”
