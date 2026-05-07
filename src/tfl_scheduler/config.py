"""
Application configuration loaded from environment variables.

Centralises all tunable settings (database URL, Transport for London API base URL,
HTTP timeouts, whether the background scheduler should start, and Flask testing
mode) in one immutable `AppConfig` object. Using a frozen dataclass makes config
easy to pass around without accidental mutation and gives a single place to document
defaults—handy in interviews when explaining how the app adapts between local dev,
Docker Compose, and tests.
"""
from dataclasses import dataclass  # `dataclass` generates `__init__`, repr, etc.; reduces boilerplate for simple config holders
import os  # Read process environment variables (12-factor style configuration)


@dataclass(frozen=True)  # `frozen=True` makes instances immutable after creation (like a typed snapshot of settings)
class AppConfig:  # Namespaced configuration for the whole Flask app and its dependencies
    database_url: str  # SQLAlchemy database URL (driver + credentials + host + DB name); required—no default in the field list because it always has a default in `from_env`
    tfl_base_url: str = "https://api.tfl.gov.uk"  # Root URL for TfL’s public REST API; can be overridden for mocking or different environments
    request_timeout_seconds: float = 10.0  # Upper bound (seconds) for outbound HTTP calls to TfL so the worker thread cannot hang indefinitely
    start_scheduler: bool = True  # When False, APScheduler is not started (e.g. in some tests or minimal API-only runs)
    testing: bool = False  # Mirrors Flask’s `TESTING` flag; toggles test-friendly behaviour when loaded from env

    @classmethod  # Factory on the class itself rather than a module-level function keeps config construction discoverable as `AppConfig.from_env()`
    def from_env(cls) -> "AppConfig":  # Builds config from `os.environ`; return type quoted because `AppConfig` is still being defined in this block
        return cls(  # Call the dataclass-generated constructor with explicit keyword arguments for clarity
            database_url=os.getenv(  # Look up DATABASE_URL or fall back to a local Postgres connection string
                "DATABASE_URL",  # Standard env var name many hosting platforms use
                "postgresql+psycopg2://tfl:tfl@localhost:5432/tfl_scheduler",  # Default: Postgres via psycopg2 on localhost (Compose uses host `postgres` instead)
            ),
            tfl_base_url=os.getenv("TFL_BASE_URL", "https://api.tfl.gov.uk"),  # Allow pointing at a stub server without code changes
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10")),  # `float(...)` because env vars are always strings at first
            start_scheduler=os.getenv("START_SCHEDULER", "true").lower() != "false",  # Treat anything except the string "false" as truthy (common env pattern)
            testing=os.getenv("FLASK_TESTING", "false").lower() == "true",  # Enable Flask testing mode only when explicitly set to true
        )
