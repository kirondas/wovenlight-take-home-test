"""
Data access layer for `Task` entities.

`TaskRepository` encapsulates all SQLAlchemy session handling, transactions, and
state transitions (create, list, update pending, delete, mark running/success/fail).
It uses short-lived sessions via a context manager so each public method is its
own transaction boundary—important when explaining thread safety with APScheduler.
`expunge` detaches ORM instances so callers can use them after the session closes
without lazy-load errors. Custom exceptions map cleanly to HTTP errors in Flask.
"""
from contextlib import contextmanager  # Factory for `@contextmanager` generator-based context managers
from sqlalchemy import select  # SQL expression construct for SELECT queries
from datetime import datetime  # Wall clock for `executed_at`
from typing import Iterator  # Type hint for context manager yield type

from .models import Task, TaskStatus  # ORM model and status enum values


class TaskRepository:  # Stateless aside from holding the session factory; all methods open/close their own session
    def __init__(self, session_factory):  # Typically `scoped_session(sessionmaker(...))` from `database.build_session_factory`
        self._session_factory = session_factory  # Stored callable: `()` returns a Session for current thread

    @contextmanager  # Allows `with self._session() as session:` pattern with commit/rollback/finally
    def _session(self) -> Iterator:  # Yields a SQLAlchemy Session; type left loose because Session class not imported here
        session = self._session_factory()  # Create or fetch thread-local Session
        try:  # Normal path
            yield session  # Body of `with` runs here
            session.commit()  # Persist changes if no exception
        except Exception:  # Any failure rolls back the whole transaction
            session.rollback()  # Undo partial writes
            raise  # Propagate original error after rollback
        finally:  # Always runs
            session.close()  # Return connection to pool / end ORM unit of work
            if hasattr(self._session_factory, "remove"):  # `scoped_session` defines `remove` to drop thread-local state
                self._session_factory.remove()  # Prevent leaking Session across unrelated uses in same thread

    def create_task(self, schedule_time: datetime, lines: list[str]) -> Task:  # Inserts a row with default id/status
        with self._session() as session:  # Transaction scope
            task = Task(schedule_time=schedule_time, lines=lines)  # Construct in-memory ORM object
            session.add(task)  # Queue INSERT
            session.flush()  # Send SQL so DB generates defaults and PK is known
            session.expunge(task)  # Detach instance from Session; safe to return after close
            return task  # Caller receives hydrated Task including id

    def get_task(self, task_id: str) -> Task | None:  # Returns detached Task or None if PK missing
        with self._session() as session:
            task = session.get(Task, task_id)  # Primary-key lookup (efficient)
            if task is not None:  # Only expunge real rows
                session.expunge(task)  # Avoid expired object after session closes
            return task  # None means “not found” for API to translate to 404

    def list_tasks(self, status: str | None = None) -> list[Task]:  # Optional filter on string status column
        with self._session() as session:
            statement = select(Task).order_by(Task.created_at)  # Stable chronological order
            if status is not None:  # Skip filter when query param absent
                statement = statement.where(Task.status == status)  # SQL WHERE clause
            tasks = list(session.scalars(statement))  # Execute and materialise rows as ORM objects
            for task in tasks:  # Detach each before session ends
                session.expunge(task)
            return tasks

    def list_pending_tasks(self) -> list[Task]:  # Convenience for scheduler reload on startup
        return self.list_tasks(status=TaskStatus.PENDING.value)  # Delegate with fixed status filter

    def update_pending_task(  # PATCH semantics: only pending rows may change schedule/lines
        self,
        task_id: str,
        schedule_time: datetime | None = None,  # None means “do not change schedule”
        lines: list[str] | None = None,  # None means “do not change lines”
    ) -> Task:
        with self._session() as session:
            task = session.get(Task, task_id)
            if task is None:  # Consistent with other mutators
                raise TaskNotFoundError(task_id)
            if task.status != TaskStatus.PENDING.value:  # Guard business rule
                raise TaskStateError("Only pending tasks can be updated.")
            if schedule_time is not None:  # Partial update support
                task.schedule_time = schedule_time
            if lines is not None:
                task.lines = lines
            task.error_message = None  # Clear stale failure info on reschedule
            task.result = None  # Clear stale success payload
            session.flush()  # Push UPDATE to DB
            session.expunge(task)
            return task

    def delete_task(self, task_id: str) -> None:  # Hard delete row
        with self._session() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            session.delete(task)  # DELETE on commit

    def mark_running(self, task_id: str) -> Task | None:  # Atomic transition pending→running; returns None if race lost
        with self._session() as session:
            task = session.get(Task, task_id)
            if task is None or task.status != TaskStatus.PENDING.value:  # Another worker or cancel may have changed state
                return None  # Caller (scheduler) should skip work
            task.status = TaskStatus.RUNNING.value
            task.error_message = None  # Fresh run
            task.result = None
            session.flush()
            session.expunge(task)
            return task

    def mark_succeeded(self, task_id: str, result: list[dict]) -> Task:  # Terminal success path
        with self._session() as session:
            task = self._get_existing(session, task_id)  # Raises if missing
            task.status = TaskStatus.SUCCEEDED.value
            task.result = result  # Store TfL JSON list
            task.error_message = None
            task.executed_at = datetime.now()
            session.flush()
            session.expunge(task)
            return task

    def mark_failed(self, task_id: str, error_message: str) -> Task:  # Terminal failure path
        with self._session() as session:
            task = self._get_existing(session, task_id)
            task.status = TaskStatus.FAILED.value
            task.result = None  # No partial result on failure
            task.error_message = error_message
            task.executed_at = datetime.now()
            session.flush()
            session.expunge(task)
            return task

    @staticmethod  # Does not need `self`; keeps helper next to methods that use it
    def _get_existing(session, task_id: str) -> Task:  # Internal helper to unify “must exist” semantics
        task = session.get(Task, task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task


class TaskNotFoundError(Exception):  # Maps to HTTP 404 in error handler for repository-originated misses
    pass


class TaskStateError(Exception):  # Maps to HTTP 409 when update violates pending-only rule
    pass
