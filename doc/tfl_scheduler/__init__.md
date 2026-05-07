# Cheat sheet: [`__init__.py`](../../src/tfl_scheduler/__init__.py)

## What this file is

The file is **intentionally empty** (no code, no imports).

Keeping an **`__init__.py`** marks `tfl_scheduler` as a **regular package** in most tooling and installers. Nothing runs when you `import tfl_scheduler` aside from registering the package.

## How you import the application

Use the app module directly:

```python
from tfl_scheduler.app import create_app
```

**Tests** (`conftest.py`) and **Docker** (`python -m tfl_scheduler.app`) already do this.

`from tfl_scheduler import create_app` will **not** work unless you add exports back into `__init__.py`.

## Interview line

> “The package root is empty on purpose — no side effects at import; the factory lives in `tfl_scheduler.app`."
