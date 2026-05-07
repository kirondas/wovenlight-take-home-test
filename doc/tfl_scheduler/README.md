# `tfl_scheduler` — interview cheat sheet index

These notes match the Python modules under [`src/tfl_scheduler/`](../../src/tfl_scheduler/). Read them in roughly this order when learning the flow end-to-end:

| Order | File | What it does |
|-------|------|----------------|
| 1 | [`__init__.md`](__init__.md) | Empty `__init__.py` — import `create_app` from `app.py`. |
| 2 | [`config.md`](config.md) | Loads settings from environment variables. |
| 3 | [`models.md`](models.md) | Database table shape (`Task`, `TaskStatus`). |
| 4 | [`database.md`](database.md) | Creates engine, tables, and DB sessions. |
| 5 | [`repository.md`](repository.md) | All SQL/ORM access in one place. |
| 6 | [`schemas.md`](schemas.md) | Validates JSON request bodies, builds JSON responses. |
| 7 | [`tfl_client.md`](tfl_client.md) | HTTP call to TfL (or any “external provider”). |
| 8 | [`scheduler.md`](scheduler.md) | Runs jobs at the right time via APScheduler. |
| 9 | [`app.md`](app.md) | Flask routes wiring everything together. |

**One-sentence story for the interviewer:** “HTTP requests hit Flask, we validate input, save a `Task` row, register a one-off job in APScheduler; when it fires we call the TfL client, then write `result` or `error_message` back to the same row.”

**If they ask “where would ML go?”** Same flow: replace or wrap `TflClient` with something that calls `/predict`; keep task lifecycle and persistence.
