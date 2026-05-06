from datetime import datetime

from tfl_scheduler.models import TaskStatus
from tfl_scheduler.tfl_client import ProviderBadResponse, ProviderTimeout


def test_scheduler_runs_task_successfully(repository, scheduler, fake_provider):
    task = repository.create_task(
        schedule_time=datetime.now(),
        lines=["victoria"],
    )

    scheduler.run_task(task.id)

    stored_task = repository.get_task(task.id)
    assert fake_provider.calls == [["victoria"]]
    assert stored_task.status == TaskStatus.SUCCEEDED.value
    assert stored_task.result == [{"description": "Minor delays"}]
    assert stored_task.error_message is None
    assert stored_task.executed_at is not None


def test_scheduler_records_provider_timeout(repository, scheduler, fake_provider):
    fake_provider.error = ProviderTimeout("Provider timed out.")
    task = repository.create_task(
        schedule_time=datetime.now(),
        lines=["central"],
    )

    scheduler.run_task(task.id)

    stored_task = repository.get_task(task.id)
    assert stored_task.status == TaskStatus.FAILED.value
    assert stored_task.error_message == "Provider timed out."
    assert stored_task.result is None


def test_scheduler_records_bad_provider_response(repository, scheduler, fake_provider):
    fake_provider.error = ProviderBadResponse("Provider returned invalid output.")
    task = repository.create_task(
        schedule_time=datetime.now(),
        lines=["central"],
    )

    scheduler.run_task(task.id)

    stored_task = repository.get_task(task.id)
    assert stored_task.status == TaskStatus.FAILED.value
    assert stored_task.error_message == "Provider returned invalid output."


def test_scheduler_records_unexpected_model_exception(
    repository,
    scheduler,
    fake_provider,
):
    fake_provider.error = RuntimeError("model weights could not be loaded")
    task = repository.create_task(
        schedule_time=datetime.now(),
        lines=["central"],
    )

    scheduler.run_task(task.id)

    stored_task = repository.get_task(task.id)
    assert stored_task.status == TaskStatus.FAILED.value
    assert "Unexpected provider execution error" in stored_task.error_message
    assert "model weights could not be loaded" in stored_task.error_message
