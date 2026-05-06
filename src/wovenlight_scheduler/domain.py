from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


SCHEDULE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

TUBE_LINE_IDS = frozenset(
    {
        "bakerloo",
        "central",
        "circle",
        "district",
        "hammersmith-city",
        "jubilee",
        "metropolitan",
        "northern",
        "piccadilly",
        "victoria",
        "waterloo-city",
    }
)


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ValidationError(ValueError):
    """Raised when an API request cannot be converted into a valid task."""


@dataclass(frozen=True)
class Task:
    id: str
    schedule_time: datetime
    lines: tuple[str, ...]
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    result: Any | None = None
    error: str | None = None
    executed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schedule_time": format_datetime(self.schedule_time),
            "lines": ",".join(self.lines),
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "created_at": format_datetime(self.created_at),
            "updated_at": format_datetime(self.updated_at),
            "executed_at": format_datetime(self.executed_at) if self.executed_at else None,
        }


def new_task_id() -> str:
    return str(uuid4())


def parse_schedule_time(raw_value: Any) -> datetime:
    if raw_value in (None, ""):
        return datetime.now().replace(microsecond=0)

    if not isinstance(raw_value, str):
        raise ValidationError("schedule_time must be a string in '%Y-%m-%dT%H:%M:%S' format")

    try:
        return datetime.strptime(raw_value, SCHEDULE_TIME_FORMAT)
    except ValueError as exc:
        raise ValidationError("schedule_time must match format '%Y-%m-%dT%H:%M:%S'") from exc


def parse_lines(raw_value: Any) -> tuple[str, ...]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValidationError("lines must be a non-empty comma-separated string of TfL line ids")

    line_ids = tuple(dict.fromkeys(part.strip().lower() for part in raw_value.split(",") if part.strip()))
    if not line_ids:
        raise ValidationError("lines must include at least one TfL line id")

    unknown = sorted(set(line_ids) - TUBE_LINE_IDS)
    if unknown:
        valid = ", ".join(sorted(TUBE_LINE_IDS))
        raise ValidationError(f"Unknown TfL line id(s): {', '.join(unknown)}. Valid ids are: {valid}")

    return line_ids


def format_datetime(value: datetime) -> str:
    return value.replace(microsecond=0).strftime(SCHEDULE_TIME_FORMAT)
