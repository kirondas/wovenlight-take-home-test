from datetime import datetime
from typing import Any

from .models import Task

SCHEDULE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

VALID_LINE_IDS = {
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


class ValidationError(Exception):
    pass


def extract_schedule_time(
    payload: dict[str, Any],
    *,
    default_to_now: bool,
) -> datetime:
    raw_value = payload.get("schedule_time")
    if raw_value in (None, ""):
        if default_to_now:
            return datetime.now().replace(microsecond=0)
        raise ValidationError("schedule_time is required.")

    if not isinstance(raw_value, str):
        raise ValidationError("schedule_time must be a string.")

    try:
        return datetime.strptime(raw_value, SCHEDULE_TIME_FORMAT)
    except ValueError as exc:
        raise ValidationError(
            f"schedule_time must match {SCHEDULE_TIME_FORMAT}."
        ) from exc


def parse_lines(raw_lines: Any, *, required: bool) -> list[str] | None:
    if raw_lines in (None, ""):
        if required:
            raise ValidationError("lines is required.")
        return None

    if not isinstance(raw_lines, str):
        raise ValidationError("lines must be a comma-separated string.")

    line_ids = []
    seen = set()
    for value in raw_lines.split(","):
        line_id = value.strip().lower()
        if not line_id:
            continue
        if line_id not in VALID_LINE_IDS:
            raise ValidationError(
                f"Unknown line id '{line_id}'. Valid ids are: "
                f"{', '.join(sorted(VALID_LINE_IDS))}."
            )
        if line_id not in seen:
            line_ids.append(line_id)
            seen.add(line_id)

    if not line_ids:
        raise ValidationError("At least one line id is required.")
    return line_ids


def serialize_task(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "schedule_time": _format_datetime(task.schedule_time),
        "lines": ",".join(task.lines),
        "status": task.status,
        "result": task.result,
        "error_message": task.error_message,
        "created_at": _format_datetime(task.created_at),
        "updated_at": _format_datetime(task.updated_at),
        "executed_at": _format_datetime(task.executed_at),
    }


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(microsecond=0).isoformat()
