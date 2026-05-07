"""
APScheduler integration: time-based execution of disruption-fetch tasks.

`TaskScheduler` bridges the persistence layer (`TaskRepository`) and the external
`DisruptionProvider` (implemented by `TflClient`). It schedules one-off `date`
jobs keyed by task id, reloads pending work after restarts, and translates provider
exceptions into `FAILED` rows. Interview narrative: contrast `date` trigger with
`interval`; explain `mark_running` returning None as optimistic concurrency; note
`max(schedule_time, now)` prevents scheduling in the past from delaying forever.
"""
import logging  # Structured-ish logs for operational visibility
from datetime import datetime  # Compare schedule wall times and compute “run no earlier than now”

from apscheduler.jobstores.base import JobLookupError  # Raised when removing a non-existent job id—safe to ignore on unschedule
from apscheduler.schedulers.background import BackgroundScheduler  # Non-blocking scheduler thread suitable for Flask

from .models import Task  # ORM entity passed in for schedule/reschedule helpers
from .repository import TaskRepository  # DB access for state transitions
from .tfl_client import DisruptionProvider, ProviderError  # Protocol for TfL and typed provider failures

logger = logging.getLogger(__name__)  # Module-level logger name for filter configuration


class TaskScheduler:  # Coordinates timed execution; owns APScheduler lifecycle
    def __init__(
        self,
        repository: TaskRepository,  # Mutates task rows as jobs run
        provider: DisruptionProvider,  # Injected for testing / alternate backends (structural typing via Protocol)
    ):
        self._repository = repository  # Stored collaborator
        self._provider = provider  # TfL HTTP client or fake
        self._scheduler = BackgroundScheduler()  # Underlying scheduler instance (started explicitly)

    def start(self) -> None:  # Idempotent start plus reload of DB-backed pending jobs
        if not self._scheduler.running:  # Avoid double-start exceptions
            self._scheduler.start()  # Spawns background thread for due jobs
        self.reload_pending_tasks()  # Ensures tasks created before crash/redeploy are still scheduled

    def shutdown(self) -> None:  # Best-effort teardown (tests or graceful shutdown hook)
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)  # Do not block current thread until jobs finish

    def schedule_task(self, task: Task) -> None:  # Add or replace APScheduler job for this task id
        run_date = max(task.schedule_time, datetime.now())  # If user picked a past instant, run ASAP instead of never
        self._scheduler.add_job(
            self.run_task,  # Callable executed by scheduler thread
            trigger="date",  # One-shot at `run_date`
            run_date=run_date,  # Concrete datetime firing time
            args=[task.id],  # Positional args to `run_task`
            id=task.id,  # Stable id enables replace_existing and remove_job by task id
            replace_existing=True,  # PATCH reschedule updates the same logical job
        )

    def reschedule_task(self, task: Task) -> None:  # Remove old fire time then enqueue new
        self.unschedule_task(task.id)
        self.schedule_task(task)

    def unschedule_task(self, task_id: str) -> None:  # Cancel pending APScheduler job if any
        try:
            self._scheduler.remove_job(task_id)
        except JobLookupError:  # Already ran, never existed, or id mismatch—non-fatal
            logger.debug(f"No scheduled job found for task {task_id}.")  # Low-noise hint for operators

    def reload_pending_tasks(self) -> None:  # Rehydrate scheduler state from database on boot
        for task in self._repository.list_pending_tasks():  # Only pending rows need future execution
            self.schedule_task(task)

    def run_task(self, task_id: str) -> None:  # Executed inside scheduler thread; must not assume Flask request context
        task = self._repository.mark_running(task_id)  # Try to claim work
        if task is None:  # Lost race: task deleted, already running, or finished
            logger.info(f"Skipping task {task_id} because it is no longer pending.")
            return

        try:
            result = self._provider.get_disruptions(task.lines)  # Network call bound by client timeouts
            self._repository.mark_succeeded(task_id, result)
        except ProviderError as exc:  # Expected failure modes (timeout, bad JSON, HTTP error)
            self._repository.mark_failed(task_id, str(exc))
        except Exception as exc:  # Safety net for unexpected bugs still marks task failed
            self._repository.mark_failed(
                task_id,
                f"Unexpected provider execution error: {exc}",
            )
