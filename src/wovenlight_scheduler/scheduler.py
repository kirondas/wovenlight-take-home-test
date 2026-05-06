from datetime import datetime
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from wovenlight_scheduler.domain import Task
from wovenlight_scheduler.repository import TaskRepository
from wovenlight_scheduler.tfl_client import TflClient, TflClientError


LOGGER = logging.getLogger(__name__)


class TaskScheduler:
    def __init__(
        self,
        repository: TaskRepository,
        tfl_client: TflClient,
        scheduler: BackgroundScheduler | None = None,
    ) -> None:
        self.repository = repository
        self.tfl_client = tfl_client
        self.scheduler = scheduler or BackgroundScheduler()

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
        self.restore_pending_tasks()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def restore_pending_tasks(self) -> None:
        for task in self.repository.get_pending():
            self.schedule(task)

    def schedule(self, task: Task) -> None:
        self.scheduler.add_job(
            func=self.run_task,
            trigger="date",
            run_date=task.schedule_time,
            args=[task.id],
            id=task.id,
            replace_existing=True,
            misfire_grace_time=None,
        )

    def reschedule(self, task: Task) -> None:
        self.cancel(task.id)
        self.schedule(task)

    def cancel(self, task_id: str) -> None:
        job = self.scheduler.get_job(task_id)
        if job:
            job.remove()

    def run_task(self, task_id: str) -> None:
        task = self.repository.get(task_id)
        if task is None:
            LOGGER.warning("Scheduled task %s no longer exists", task_id)
            return

        if task.schedule_time > datetime.now():
            LOGGER.info("Task %s fired early; rescheduling", task.id)
            self.schedule(task)
            return

        self.repository.mark_running(task.id)
        try:
            result = self.tfl_client.get_line_disruptions(task.lines)
        except TflClientError as exc:
            LOGGER.exception("Task %s failed while calling TfL", task.id)
            self.repository.mark_failed(task.id, str(exc))
            return
        except Exception as exc:
            LOGGER.exception("Task %s failed unexpectedly", task.id)
            self.repository.mark_failed(task.id, f"Unexpected scheduler error: {exc}")
            return

        self.repository.mark_completed(task.id, result)
