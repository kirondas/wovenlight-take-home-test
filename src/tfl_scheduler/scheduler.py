from datetime import datetime
import logging

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler

from .models import Task
from .repository import TaskRepository
from .tfl_client import DisruptionProvider, ProviderError

logger = logging.getLogger(__name__)


class TaskScheduler:
    def __init__(
        self,
        repository: TaskRepository,
        provider: DisruptionProvider,
    ):
        self._repository = repository
        self._provider = provider
        self._scheduler = BackgroundScheduler()

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
        self.reload_pending_tasks()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def schedule_task(self, task: Task) -> None:
        run_date = max(task.schedule_time, datetime.now())
        self._scheduler.add_job(
            self.run_task,
            trigger="date",
            run_date=run_date,
            args=[task.id],
            id=task.id,
            replace_existing=True,
        )

    def reschedule_task(self, task: Task) -> None:
        self.unschedule_task(task.id)
        self.schedule_task(task)

    def unschedule_task(self, task_id: str) -> None:
        try:
            self._scheduler.remove_job(task_id)
        except JobLookupError:
            logger.debug("No scheduled job found for task %s.", task_id)

    def reload_pending_tasks(self) -> None:
        for task in self._repository.list_pending_tasks():
            self.schedule_task(task)

    def run_task(self, task_id: str) -> None:
        task = self._repository.mark_running(task_id)
        if task is None:
            logger.info("Skipping task %s because it is no longer pending.", task_id)
            return

        try:
            result = self._provider.get_disruptions(task.lines)
            self._repository.mark_succeeded(task_id, result)
        except ProviderError as exc:
            self._repository.mark_failed(task_id, str(exc))
        except Exception as exc:  # noqa: BLE001 - record model/runtime failures.
            self._repository.mark_failed(
                task_id,
                f"Unexpected provider execution error: {exc}",
            )
