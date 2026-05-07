"""
Request validation and JSON serialisation helpers for task resources.

Turns untyped JSON bodies into strict Python types (`datetime`, list of line ids)
and turns ORM `Task` rows into JSON-friendly dictionaries for Flask responses.
Keeps HTTP handlers thin by centralising parsing rules such as allowed TfL line
identifiers and timestamp format. Interview tip: contrast `ValidationError` raised
here with repository `TaskNotFoundError`—the former is client mistakes (400), the
latter missing data (404/409 depending on route).
"""
from datetime import datetime  # Parsed schedule times and normalized output formatting
from typing import Any  # JSON payloads are heterogeneous until validated

from .models import Task  # ORM entity we expose through `serialise_task`

SCHEDULE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"  # Strict format without timezone or fractional seconds (matches API contract)

VALID_LINE_IDS = {  # Closed set of TfL line ids accepted by this service (subset of tube / rail lines)
    "bakerloo",  # Line identifier as used in TfL unified API paths
    "central",  # London Underground line id
    "circle",  # London Underground line id
    "district",  # London Underground line id
    "hammersmith-city",  # London Underground line id (hyphenated slug)
    "jubilee",  # London Underground line id
    "metropolitan",  # London Underground line id
    "northern",  # London Underground line id
    "piccadilly",  # London Underground line id
    "victoria",  # London Underground line id
    "waterloo-city",  # London Underground line id
}


class ValidationError(Exception):  # Domain-specific “bad input” signal converted to HTTP 400 in the error handler
    pass  # No extra fields—message string carries detail for API clients


def extract_schedule_time(  # Pulls and parses `schedule_time` from a JSON dict
    payload: dict[str, Any],  # Raw decoded JSON object from Flask
    *,  # Keyword-only params after this point so callers must name `default_to_now`
    default_to_now: bool,  # When True, missing schedule means “run ASAP”; when False, missing is an error
) -> datetime:  # Always returns naive datetime in local interpretation (no tz in format)
    raw_value = payload.get("schedule_time")  # May be str, wrong type, or absent
    if raw_value in (None, ""):  # Treat explicit JSON null or empty string as “missing”
        if default_to_now:  # Create path uses default; strict update paths pass False elsewhere
            return datetime.now().replace(microsecond=0)  # Strip microseconds to match parse format granularity
        raise ValidationError("schedule_time is required.")  # Caller requested strict presence

    if not isinstance(raw_value, str):  # Reject numbers/objects early with a clear message
        raise ValidationError("schedule_time must be a string.")

    try:  # `strptime` raises ValueError on mismatch
        return datetime.strptime(raw_value, SCHEDULE_TIME_FORMAT)  # Parse fixed format into datetime
    except ValueError as exc:  # Attach context while preserving chain for debugging
        raise ValidationError(
            f"schedule_time must match {SCHEDULE_TIME_FORMAT}."
        ) from exc


def parse_lines(raw_lines: Any, *, required: bool) -> list[str] | None:  # Normalises comma-separated string into deduped lowercase ids
    if raw_lines in (None, ""):  # Field omitted or empty
        if required:  # POST /tasks requires lines
            raise ValidationError("lines is required.")
        return None  # PATCH may omit lines to mean “leave unchanged”

    if not isinstance(raw_lines, str):  # API contract uses a single CSV string, not JSON array
        raise ValidationError("lines must be a comma-separated string.")

    line_ids = []  # Accumulator preserving first-seen order
    seen = set()  # Tracks duplicates without O(n^2) scans
    for value in raw_lines.split(","):  # Split on commas allowing spaces around tokens
        line_id = value.strip().lower()  # Normalise whitespace and casing to match `VALID_LINE_IDS`
        if not line_id:  # Skip empty segments from trailing commas etc.
            continue  # Next token
        if line_id not in VALID_LINE_IDS:  # Reject unknown lines to avoid bad upstream API calls
            raise ValidationError(
                f"Unknown line '{line_id}'. Valid lines are: "
                f"{', '.join(sorted(VALID_LINE_IDS))}."
            )
        if line_id not in seen:  # Preserve order but drop duplicates
            line_ids.append(line_id)  # Record unique id
            seen.add(line_id)  # Mark as seen

    if not line_ids:  # After filtering empties, require at least one real line
        raise ValidationError("At least one line is required.")
    return line_ids


def serialise_task(task: Task) -> dict[str, Any]:  # Convert ORM model to plain dict for `jsonify`
    return {  # Explicit key order not required by JSON but readable for humans
        "id": task.id,  # UUID primary key string
        "schedule_time": _format_datetime(task.schedule_time),  # ISO-like string without microseconds
        "lines": ",".join(task.lines),  # Recreate CSV form expected by clients
        "status": task.status,  # String mirror of enum
        "result": task.result,  # None or list of dicts from provider
        "error_message": task.error_message,  # None or error text
        "created_at": _format_datetime(task.created_at),  # Audit fields
        "updated_at": _format_datetime(task.updated_at),  # Last mutation time from ORM `onupdate`
        "executed_at": _format_datetime(task.executed_at),  # None until terminal state written
    }


def _format_datetime(value: datetime | None) -> str | None:  # Normalises optional datetimes for JSON
    if value is None:  # Not yet executed or not applicable
        return None  # JSON null via Flask encoding
    return value.replace(microsecond=0).isoformat()  # ISO 8601 string consistent with no-microsecond policy
