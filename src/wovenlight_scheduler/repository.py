from collections.abc import Mapping
from datetime import datetime
import json
import threading
from typing import Any

import psycopg
from psycopg.rows import dict_row

from wovenlight_scheduler.domain import Task, TaskStatus, format_datetime, new_task_id

_TASK_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    schedule_time TEXT NOT NULL,
    lines TEXT NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    executed_at TEXT
)
"""


def _encode_lines(lines: tuple[str, ...]) -> str:
    return json.dumps(list(lines))


def _decode_datetime(value: str | None) -> datetime | None:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S") if value else None


def task_from_db_row(row: Mapping[str, Any]) -> Task:
    result_raw = row["result_json"]
    return Task(
        id=row["id"],
        schedule_time=_decode_datetime(row["schedule_time"]),
        lines=tuple(json.loads(row["lines"])),
        status=TaskStatus(row["status"]),
        result=json.loads(result_raw) if result_raw else None,
        error=row["error"],
        created_at=_decode_datetime(row["created_at"]),
        updated_at=_decode_datetime(row["updated_at"]),
        executed_at=_decode_datetime(row["executed_at"]),
    )


class TaskRepository:
    """PostgreSQL persistence for tasks."""

    def __init__(self, database_url: str) -> None:
        self._dsn = database_url
        self._lock = threading.RLock()
        self.initialise()

    def initialise(self) -> None:
        with psycopg.connect(self._dsn) as connection:
            connection.execute(_TASK_SCHEMA)
            connection.commit()

    def create(self, schedule_time: datetime, lines: tuple[str, ...]) -> Task:
        now = datetime.now().replace(microsecond=0)
        task = Task(
            id=new_task_id(),
            schedule_time=schedule_time,
            lines=lines,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        with self._lock, psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            connection.execute(
                """
                INSERT INTO tasks (id, schedule_time, lines, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    task.id,
                    format_datetime(task.schedule_time),
                    _encode_lines(task.lines),
                    task.status.value,
                    format_datetime(task.created_at),
                    format_datetime(task.updated_at),
                ),
            )
            connection.commit()
        return task

    def list_tasks(self) -> list[Task]:
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            rows = connection.execute("SELECT * FROM tasks ORDER BY created_at").fetchall()
        return [task_from_db_row(row) for row in rows]

    def get(self, task_id: str) -> Task | None:
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()
        return task_from_db_row(row) if row else None

    def get_pending(self) -> list[Task]:
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            rows = connection.execute(
                "SELECT * FROM tasks WHERE status = %s ORDER BY schedule_time",
                (TaskStatus.PENDING.value,),
            ).fetchall()
        return [task_from_db_row(row) for row in rows]

    def update_pending(
        self,
        task_id: str,
        *,
        schedule_time: datetime | None = None,
        lines: tuple[str, ...] | None = None,
    ) -> Task | None:
        with self._lock:
            task = self.get(task_id)
            if task is None or task.status is not TaskStatus.PENDING:
                return None

            next_schedule_time = schedule_time or task.schedule_time
            next_lines = lines or task.lines
            now = datetime.now().replace(microsecond=0)

            with psycopg.connect(self._dsn) as connection:
                connection.execute(
                    """
                    UPDATE tasks
                    SET schedule_time = %s, lines = %s, updated_at = %s
                    WHERE id = %s AND status = %s
                    """,
                    (
                        format_datetime(next_schedule_time),
                        _encode_lines(next_lines),
                        format_datetime(now),
                        task_id,
                        TaskStatus.PENDING.value,
                    ),
                )
                connection.commit()
        return self.get(task_id)

    def mark_running(self, task_id: str) -> Task | None:
        return self._set_status(task_id, TaskStatus.RUNNING)

    def mark_completed(self, task_id: str, result: Any) -> Task | None:
        now = datetime.now().replace(microsecond=0)
        with self._lock, psycopg.connect(self._dsn) as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = %s, result_json = %s, error = NULL, updated_at = %s, executed_at = %s
                WHERE id = %s
                """,
                (
                    TaskStatus.COMPLETED.value,
                    json.dumps(result),
                    format_datetime(now),
                    format_datetime(now),
                    task_id,
                ),
            )
            connection.commit()
        return self.get(task_id)

    def mark_failed(self, task_id: str, error: str) -> Task | None:
        now = datetime.now().replace(microsecond=0)
        with self._lock, psycopg.connect(self._dsn) as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = %s, error = %s, updated_at = %s, executed_at = %s
                WHERE id = %s
                """,
                (
                    TaskStatus.FAILED.value,
                    error,
                    format_datetime(now),
                    format_datetime(now),
                    task_id,
                ),
            )
            connection.commit()
        return self.get(task_id)

    def mark_cancelled(self, task_id: str) -> Task | None:
        return self._set_status(task_id, TaskStatus.CANCELLED)

    def _set_status(self, task_id: str, status: TaskStatus) -> Task | None:
        now = datetime.now().replace(microsecond=0)
        with self._lock, psycopg.connect(self._dsn) as connection:
            connection.execute(
                "UPDATE tasks SET status = %s, updated_at = %s WHERE id = %s",
                (status.value, format_datetime(now), task_id),
            )
            connection.commit()
        return self.get(task_id)
