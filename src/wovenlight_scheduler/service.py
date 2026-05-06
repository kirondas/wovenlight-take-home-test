from typing import Any

from wovenlight_scheduler.domain import Task, TaskStatus, parse_lines, parse_schedule_time
from wovenlight_scheduler.repository import TaskRepository
from wovenlight_scheduler.scheduler import TaskScheduler


class TaskNotFoundError(LookupError):
    pass


class TaskAlreadyExecutedError(RuntimeError):
    pass


class TaskService:
    def __init__(self, repository: TaskRepository, scheduler: TaskScheduler) -> None:
        self.repository = repository
        self.scheduler = scheduler

    def create_task(self, payload: dict[str, Any]) -> Task:
        schedule_time = parse_schedule_time(_schedule_time_value(payload))
        lines = parse_lines(payload.get("lines"))
        task = self.repository.create(schedule_time=schedule_time, lines=lines)
        self.scheduler.schedule(task)
        return task

    def list_tasks(self) -> list[Task]:
        return self.repository.list_tasks()

    def get_task(self, task_id: str) -> Task:
        task = self.repository.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    def update_task(self, task_id: str, payload: dict[str, Any]) -> Task:
        existing = self.get_task(task_id)
        if existing.status is not TaskStatus.PENDING:
            raise TaskAlreadyExecutedError("Only pending tasks can be updated")

        schedule_time = None
        lines = None
        if "schedule_time" in payload or "scheduler_time" in payload:
            schedule_time = parse_schedule_time(_schedule_time_value(payload))
        if "lines" in payload:
            lines = parse_lines(payload.get("lines"))
        if schedule_time is None and lines is None:
            return existing

        updated = self.repository.update_pending(task_id, schedule_time=schedule_time, lines=lines)
        if updated is None:
            raise TaskAlreadyExecutedError("Only pending tasks can be updated")
        self.scheduler.reschedule(updated)
        return updated

    def delete_task(self, task_id: str) -> None:
        task = self.get_task(task_id)
        if task.status is TaskStatus.PENDING:
            self.scheduler.cancel(task_id)
        self.repository.mark_cancelled(task_id)


def _schedule_time_value(payload: dict[str, Any]) -> Any:
    return payload.get("schedule_time", payload.get("scheduler_time"))
