from datetime import datetime, timedelta

from wovenlight_scheduler.repository import TaskRepository
from wovenlight_scheduler.scheduler import TaskScheduler
from wovenlight_scheduler.tfl_client import TflClientError


class FakeTflClient:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result if result is not None else [{"description": "Minor delays"}]
        self.error = error
        self.calls: list[tuple[str, ...]] = []

    def get_line_disruptions(self, lines: tuple[str, ...]):
        self.calls.append(lines)
        if self.error:
            raise self.error
        return self.result


def test_run_task_stores_tfl_result(postgresql_url: str) -> None:
    repository = TaskRepository(postgresql_url)
    task = repository.create(datetime.now() - timedelta(seconds=1), ("victoria",))
    tfl_client = FakeTflClient(result=[{"line": "victoria"}])
    scheduler = TaskScheduler(repository, tfl_client)

    scheduler.run_task(task.id)

    updated = repository.get(task.id)
    assert updated.result == [{"line": "victoria"}]
    assert updated.status.value == "completed"
    assert tfl_client.calls == [("victoria",)]


def test_run_task_stores_failure(postgresql_url: str) -> None:
    repository = TaskRepository(postgresql_url)
    task = repository.create(datetime.now() - timedelta(seconds=1), ("victoria",))
    scheduler = TaskScheduler(repository, FakeTflClient(error=TflClientError("TfL unavailable")))

    scheduler.run_task(task.id)

    updated = repository.get(task.id)
    assert updated.status.value == "failed"
    assert updated.error == "TfL unavailable"


def test_restore_pending_tasks_registers_jobs(postgresql_url: str) -> None:
    repository = TaskRepository(postgresql_url)
    task = repository.create(datetime.now() + timedelta(hours=1), ("victoria",))
    scheduler = TaskScheduler(repository, FakeTflClient())

    scheduler.scheduler.start(paused=True)
    try:
        scheduler.restore_pending_tasks()
        assert scheduler.scheduler.get_job(task.id) is not None
    finally:
        scheduler.shutdown()
