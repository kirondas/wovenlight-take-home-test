from datetime import datetime

import pytest

from tfl_scheduler.app import create_app
from tfl_scheduler.config import AppConfig


class FakeProvider:
    def __init__(self):
        self.result = [{"description": "Minor delays"}]
        self.error = None
        self.calls = []

    def get_disruptions(self, lines):
        self.calls.append(lines)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture()
def fake_provider():
    return FakeProvider()


@pytest.fixture()
def app(fake_provider):
    application = create_app(
        AppConfig(
            database_url="sqlite:///:memory:",
            start_scheduler=False,
            testing=True,
        ),
        provider=fake_provider,
    )
    yield application
    application.extensions["task_scheduler"].shutdown()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def repository(app):
    return app.extensions["task_repository"]


@pytest.fixture()
def scheduler(app):
    return app.extensions["task_scheduler"]


def future_time() -> str:
    return datetime(2099, 1, 1, 17, 0, 0).isoformat()
