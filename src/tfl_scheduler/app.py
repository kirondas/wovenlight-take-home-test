"""
Flask HTTP application factory and route wiring.

`create_app` constructs the Flask instance, loads configuration, builds the database
session factory and repository, instantiates the TfL client and background scheduler,
optionally starts scheduling, and registers REST routes plus error handlers.
Handlers stay thin: validate JSON via `schemas`, delegate persistence to
`TaskRepository`, and enqueue work through `TaskScheduler`. This file is the usual
entry point for interview walkthroughs of request/response flow and extension
registry usage (`app.extensions[...]`).
"""
from flask import Flask, jsonify, request  # Flask app factory, JSON responses, and access to query/body
from http import HTTPStatus  # Named status codes instead of magic integers
import os  # Read bind host/port env vars when running `python -m tfl_scheduler.app`

from .config import AppConfig  # Immutable settings loaded from environment (or injected in tests)
from .database import build_session_factory  # SQLAlchemy engine + scoped_session factory
from .models import TaskStatus  # Allowed status tokens for filtering/validation
from .repository import TaskNotFoundError, TaskRepository, TaskStateError  # Persistence and domain errors
from .scheduler import TaskScheduler  # APScheduler bridge
from .schemas import (  # Validation/parsing helpers keep route functions small
    ValidationError,  # Bad client input from parsing helpers
    extract_schedule_time,  # Parse/normalise schedule field
    parse_lines,  # Parse CSV line ids
    serialise_task,  # ORM → dict for JSON
)  # Closing paren ends the multi-line import list
from .tfl_client import DisruptionProvider, TflClient  # Protocol + concrete HTTP client


def create_app(  # Factory lets tests/config pass deps without global state
    config: AppConfig | None = None,  # Optional injection for tests; None means read real env
    provider: DisruptionProvider | None = None,  # Optional fake TfL for tests; None builds real `TflClient`
) -> Flask:  # Application factory pattern: delay side effects until this runs
    config = config or AppConfig.from_env()  # Replace None with env-derived defaults
    app = Flask(__name__)  # `__name__` helps Flask locate resources relative to the package
    app.config["TESTING"] = config.testing  # Flask built-in flag changes some behaviours (e.g. error propagation)

    session_factory, _ = build_session_factory(config.database_url)  # Discard engine in production path
    repository = TaskRepository(session_factory)  # Shared DB access object
    disruption_provider = provider or TflClient(  # Dependency injection of provider implementation
        base_url=config.tfl_base_url,  # From env: TFL_BASE_URL
        timeout_seconds=config.request_timeout_seconds,  # From env: REQUEST_TIMEOUT_SECONDS
    )  # Instantiate real client only when tests did not pass a stub `provider`
    task_scheduler = TaskScheduler(repository, disruption_provider)  # Background execution coordinator

    app.extensions["task_repository"] = repository  # Discoverable hook for tests/extensions
    app.extensions["task_scheduler"] = task_scheduler

    if config.start_scheduler:  # Can disable for unit tests hitting routes only
        task_scheduler.start()  # Start APScheduler thread and reload pending rows

    register_routes(app, repository, task_scheduler)  # Attach URL rules
    register_error_handlers(app)  # Map Python exceptions to JSON errors
    return app


def register_routes(  # Nested view functions close over these collaborators (closure)
    app: Flask,  # Flask instance receiving route decorators
    repository: TaskRepository,  # DB access for CRUD
    task_scheduler: TaskScheduler,  # In-process scheduler for enqueue/cancel/reschedule
) -> None:  # Side effect: mutates `app` routing table
    @app.get("/health")  # Shallow readiness probe for load balancers
    def health() -> tuple[dict[str, str], int]:  # Flask allows returning (body, status)
        return {"status": "ok"}, HTTPStatus.OK  # Minimal JSON payload

    @app.post("/tasks")  # Create a new scheduled fetch task
    def create_task():  # Function name is only for stack traces; URL is what matters
        payload = _json_payload()  # Ensures JSON object body
        schedule_time = extract_schedule_time(payload, default_to_now=True)  # Default “now” if omitted
        lines = parse_lines(payload.get("lines"), required=True)  # Must include lines on create

        task = repository.create_task(schedule_time=schedule_time, lines=lines)  # Persist PENDING row
        task_scheduler.schedule_task(task)  # Register APScheduler job by task id
        return jsonify(serialise_task(task)), HTTPStatus.CREATED  # 201 + representation

    @app.get("/tasks")  # Collection listing with optional filter
    def list_tasks():  # Reads `?status=` query string
        status = request.args.get("status")  # Returns None if parameter absent
        if status and status not in TaskStatus.values():  # Reject unknown filters early
            raise ValidationError(
                f"status must be one of: {', '.join(TaskStatus.values())}"  # Dynamic message lists allowed enum values
            )  # Becomes HTTP 400 via `register_error_handlers`

        tasks = repository.list_tasks(status=status)  # None status → no WHERE clause
        return jsonify([serialise_task(task) for task in tasks]), HTTPStatus.OK

    @app.get("/tasks/<task_id>")  # Single resource read
    def get_task(task_id: str):  # `task_id` captured from URL path
        task = repository.get_task(task_id)  # Detached ORM object or None
        if task is None:  # Distinguish missing id without exceptions in happy path
            return _error("not_found", "Task not found.", HTTPStatus.NOT_FOUND)
        return jsonify(serialise_task(task)), HTTPStatus.OK

    @app.patch("/tasks/<task_id>")  # Partial update for pending tasks only (enforced in repo + here)
    def update_task(task_id: str):  # HTTP PATCH handler
        existing_task = repository.get_task(task_id)  # Load current row before mutating
        if existing_task is None:  # Same 404 shape as GET /tasks/:id
            return _error("not_found", "Task not found.", HTTPStatus.NOT_FOUND)
        if existing_task.status != TaskStatus.PENDING.value:  # Business rule also checked in repository
            return _error(
                "task_not_pending",  # Stable machine-readable error code for clients
                "Only pending tasks can be updated.",  # Human-readable detail
                HTTPStatus.CONFLICT,  # 409: resource exists but wrong state
            )

        payload = _json_payload()  # Validates JSON object body
        has_schedule_time = "schedule_time" in payload  # Key presence distinguishes omit vs explicit null (handled upstream)
        has_lines = "lines" in payload  # True when client intends to replace line list
        if not has_schedule_time and not has_lines:  # PATCH must change something
            raise ValidationError("Provide schedule_time and/or lines to update.")

        schedule_time = (  # Conditional parsing avoids requiring schedule when only lines change
            extract_schedule_time(payload, default_to_now=True)  # Parse string when key is present; default rarely used if value present
            if has_schedule_time
            else None  # None signals repository “leave schedule alone”
        )
        lines = parse_lines(payload.get("lines"), required=False) if has_lines else None  # `required=False`: validate shape without “missing lines” error

        updated_task = repository.update_pending_task(  # May raise TaskNotFoundError/TaskStateError
            task_id=task_id,  # Primary key string from URL
            schedule_time=schedule_time,  # Parsed datetime or None (partial update)
            lines=lines,  # Normalised ids or None (partial update)
        )
        task_scheduler.reschedule_task(updated_task)  # Replace APScheduler job with new run time
        return jsonify(serialise_task(updated_task)), HTTPStatus.OK

    @app.delete("/tasks/<task_id>")  # Removes row unless RUNNING
    def delete_task(task_id: str):  # HTTP DELETE handler
        task = repository.get_task(task_id)  # Need status to enforce RUNNING guard
        if task is None:
            return _error("not_found", "Task not found.", HTTPStatus.NOT_FOUND)
        if task.status == TaskStatus.RUNNING.value:  # Avoid deleting in-flight work
            return _error(
                "task_running",  # Specific code clients can branch on
                "Running tasks cannot be deleted.",  # Explains 409
                HTTPStatus.CONFLICT,  # Conflict: state forbids operation
            )

        if task.status == TaskStatus.PENDING.value:  # Cancel scheduled execution if still queued
            task_scheduler.unschedule_task(task_id)
        repository.delete_task(task_id)  # Repo raises if a race deleted the row first
        return "", HTTPStatus.NO_CONTENT  # 204 semantics: empty body


def register_error_handlers(app: Flask) -> None:  # Central JSON error envelope
    @app.errorhandler(ValidationError)  # Raised from schema helpers and manual checks
    def handle_validation_error(error: ValidationError):  # Flask passes the exception instance
        return _error("validation_error", str(error), HTTPStatus.BAD_REQUEST)

    @app.errorhandler(404)  # Unregistered routes
    def handle_missing_route(_error_value):  # Leading underscore: intentionally unused (avoids shadowing `_error`)
        return _error("not_found", "Route not found.", HTTPStatus.NOT_FOUND)

    @app.errorhandler(TaskNotFoundError)  # From repository on updates/deletes when id missing
    def handle_task_not_found(_error_value):  # Repository raised TaskNotFoundError
        return _error("not_found", "Task not found.", HTTPStatus.NOT_FOUND)

    @app.errorhandler(TaskStateError)  # Illegal state transition surfaced as 409
    def handle_task_state_error(error: TaskStateError):  # e.g. update on non-pending row inside repository
        return _error("task_not_pending", str(error), HTTPStatus.CONFLICT)


def _json_payload() -> dict:  # Private helper—leading underscore signals internal use
    payload = request.get_json(silent=True)  # Parse JSON; `silent=True` returns None on invalid body instead of 400 here
    if not isinstance(payload, dict):  # Require object at top-level, not array/string/null
        raise ValidationError("Request body must be a JSON object.")
    return payload


def _error(code: str, message: str, status: HTTPStatus):  # Consistent error JSON shape across routes/handlers
    return jsonify({"error": {"code": code, "message": message}}), status


if __name__ == "__main__":  # Running this module directly (not via Flask CLI or gunicorn)
    application = create_app()  # Build with default env config
    application.run(  # Dev server only; production would use a WSGI server
        host=os.getenv("FLASK_HOST", "127.0.0.1"),  # Bind address; Docker sets 0.0.0.0
        port=int(os.getenv("FLASK_PORT", "5555")),  # Cast env string to int for Flask’s dev server
    )  # Blocks until process exit (foreground server)
