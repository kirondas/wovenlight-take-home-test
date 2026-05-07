"""
tfl_scheduler package marker.

This file turns the `tfl_scheduler` directory into a proper Python package so imports
like `from tfl_scheduler.app import create_app` work when the project is installed
(e.g. via pip). Keeping this module minimal avoids import cycles and side effects at
import time; the real application code lives in sibling modules (`app`, `config`,
`database`, etc.). Interview note: empty or tiny `__init__.py` files are common in
service-style layouts where the package is just a namespace, not a library API.
"""
# No imports or __all__: consumers import submodules directly (avoids import-time coupling).
