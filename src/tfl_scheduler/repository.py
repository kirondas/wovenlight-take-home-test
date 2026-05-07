from contextlib import contextmanager
from sqlalchemy import select
from datetime import datetime
from typing import Iterator

from .models import Task, TaskStatus


class TaskRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @contextmanager
    def _session(self) -> Iterator:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            if hasattr(self._session_factory, "remove"):
                self._session_factory.remove()

    def create_task(self, schedule_time: datetime, lines: list[str]) -> Task:
        with self._session() as session:
            task = Task(schedule_time=schedule_time, lines=lines)
            session.add(task)
            session.flush()
            session.expunge(task)
            return task

    def get_task(self, task_id: str) -> Task | None:
        with self._session() as session:
            task = session.get(Task, task_id)
            if task is not None:
                session.expunge(task)
            return task

    def list_tasks(self, status: str | None = None) -> list[Task]:
        with self._session() as session:
            statement = select(Task).order_by(Task.created_at)
            if status is not None:
                statement = statement.where(Task.status == status)
            tasks = list(session.scalars(statement))
            for task in tasks:
                session.expunge(task)
            return tasks

    def list_pending_tasks(self) -> list[Task]:
        return self.list_tasks(status=TaskStatus.PENDING.value)

    def update_pending_task(
        self,
        task_id: str,
        schedule_time: datetime | None = None,
        lines: list[str] | None = None,
    ) -> Task:
        with self._session() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            if task.status != TaskStatus.PENDING.value:
                raise TaskStateError("Only pending tasks can be updated.")
            if schedule_time is not None:
                task.schedule_time = schedule_time
            if lines is not None:
                task.lines = lines
            task.error_message = None
            task.result = None
            session.flush()
            session.expunge(task)
            return task

    def delete_task(self, task_id: str) -> None:
        with self._session() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            session.delete(task)

    def mark_running(self, task_id: str) -> Task | None:
        with self._session() as session:
            task = session.get(Task, task_id)
            if task is None or task.status != TaskStatus.PENDING.value:
                return None
            task.status = TaskStatus.RUNNING.value
            task.error_message = None
            task.result = None
            session.flush()
            session.expunge(task)
            return task

    def mark_succeeded(self, task_id: str, result: list[dict]) -> Task:
        with self._session() as session:
            task = self._get_existing(session, task_id)
            task.status = TaskStatus.SUCCEEDED.value
            task.result = result
            task.error_message = None
            task.executed_at = datetime.now()
            session.flush()
            session.expunge(task)
            return task

    def mark_failed(self, task_id: str, error_message: str) -> Task:
        with self._session() as session:
            task = self._get_existing(session, task_id)
            task.status = TaskStatus.FAILED.value
            task.result = None
            task.error_message = error_message
            task.executed_at = datetime.now()
            session.flush()
            session.expunge(task)
            return task

    @staticmethod
    def _get_existing(session, task_id: str) -> Task:
        task = session.get(Task, task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task


class TaskNotFoundError(Exception):
    pass


class TaskStateError(Exception):
    pass
