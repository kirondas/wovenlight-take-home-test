from collections.abc import Iterator
import os
from typing import Any

import pytest

from wovenlight_scheduler.app import create_app
from wovenlight_scheduler.config import Config


def _normalize_postgres_url(raw: str) -> str:
    if "://" not in raw:
        return raw
    scheme, _, rest = raw.partition("://")
    base = scheme.split("+", 1)[0]
    return f"{base}://{rest}"


@pytest.fixture(scope="session")
def postgresql_url() -> Iterator[str]:
    """PostgreSQL URL for tests: ``TEST_DATABASE_URL`` or Testcontainers (needs Docker)."""
    explicit = os.environ.get("TEST_DATABASE_URL", "").strip()
    if explicit:
        yield _normalize_postgres_url(explicit)
        return

    pytest.importorskip(
        "testcontainers",
        reason="pip install '.[dev]' and run Docker, or set TEST_DATABASE_URL to a Postgres URL",
    )
    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer("postgres:16-alpine")
    container.start()
    try:
        yield _normalize_postgres_url(container.get_connection_url())
    finally:
        container.stop()


class ImmediateScheduler:
    def __init__(self) -> None:
        self.scheduled: list[str] = []
        self.cancelled: list[str] = []

    def schedule(self, task) -> None:
        self.scheduled.append(task.id)

    def reschedule(self, task) -> None:
        self.cancel(task.id)
        self.schedule(task)

    def cancel(self, task_id: str) -> None:
        self.cancelled.append(task_id)

    def start(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


@pytest.fixture()
def app(postgresql_url: str):
    scheduler = ImmediateScheduler()
    config = Config(database_url=postgresql_url, start_scheduler=False)
    flask_app = create_app(config, task_scheduler=scheduler)
    flask_app.config.update(TESTING=True)
    flask_app.extensions["test_scheduler"] = scheduler
    return flask_app


@pytest.fixture()
def client(app: Any) -> Iterator[Any]:
    with app.test_client() as test_client:
        yield test_client
