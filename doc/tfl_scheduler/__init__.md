# Cheat sheet: [`__init__.py`](../../src/tfl_scheduler/__init__.py)

## What this file is

In Python, a **package** is usually a folder that contains an `__init__.py` file. Without it (in older Python setups) the folder might not be treated as an importable package. Today it is still conventional: it runs when you `import tfl_scheduler`.

This file is tiny on purpose.

## What the code does

```python
from .app import create_app
```

- The leading dot (`.app`) means **“import from the same package”** — i.e. the module `tfl_scheduler/app.py`.
- So `create_app` is really defined in `app.py`, but re-exported here.

```python
__all__ = ["create_app"]
```

- `__all__` documents the **public surface** of the package: “if someone does `from tfl_scheduler import *`, only export `create_app`.”
- In real code, star-imports are rare, but `__all__` still signals: *this is what we intend external users to use*.

## Why this pattern exists

### 1. Nicer import paths

Callers can write either:

- `from tfl_scheduler import create_app`  (short, uses `__init__.py`)

or

- `from tfl_scheduler.app import create_app`  (explicit)

Both work. The interview point: **we picked a clear entry point** (`create_app`) so production and tests have one obvious function to build the app.

### 2. App factory + tests

`create_app` is an **application factory**: it *returns* a Flask app object instead of creating a single global `app` at import time. That matters because **tests** can call `create_app()` with a fake database URL or a fake TfL client without fighting global state.

## What you should say in review

> “`__init__.py` marks this directory as a package and re-exports `create_app` so the entry point is obvious. The real implementation lives in `app.py`.”

## Common follow-up questions

**Q: Could `__init__.py` be empty?**  
Yes. An empty file still marks a package. You would lose the convenience import unless you always import from `.app`.

**Q: Could we delete it?**  
On modern Python / certain packaging layouts, sometimes — but for a take-home, keeping it avoids confusion and matches most teams’ conventions.
