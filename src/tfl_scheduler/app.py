from http import HTTPStatus
import os

from flask import Flask, jsonify, request

from .config import AppConfig
from .database import build_session_factory
from .models import TaskStatus
from .repository import TaskNotFoundError, TaskRepository, TaskStateError
from .scheduler import TaskScheduler
from .schemas import (
    ValidationError,
    extract_schedule_time,
    parse_lines,
    serialize_task,
)
from .tfl_client import DisruptionProvider, TflClient


def create_app(
    config: AppConfig | None = None,
    provider: DisruptionProvider | None = None,
) -> Flask:
    config = config or AppConfig.from_env()
    app = Flask(__name__)
    app.config["TESTING"] = config.testing

    session_factory, engine = build_session_factory(config.database_url)
    repository = TaskRepository(session_factory)
    disruption_provider = provider or TflClient(
        base_url=config.tfl_base_url,
        timeout_seconds=config.request_timeout_seconds,
    )
    task_scheduler = TaskScheduler(repository, disruption_provider)

    app.extensions["db_engine"] = engine
    app.extensions["session_factory"] = session_factory
    app.extensions["task_repository"] = repository
    app.extensions["task_scheduler"] = task_scheduler

    if config.start_scheduler:
        task_scheduler.start()

    register_routes(app, repository, task_scheduler)
    register_error_handlers(app)
    return app


def register_routes(
    app: Flask,
    repository: TaskRepository,
    task_scheduler: TaskScheduler,
) -> None:
    @app.get("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, HTTPStatus.OK

    @app.post("/tasks")
    def create_task():
        payload = _json_payload()
        schedule_time = extract_schedule_time(payload, default_to_now=True)
        lines = parse_lines(payload.get("lines"), required=True)

        task = repository.create_task(schedule_time=schedule_time, lines=lines)
        task_scheduler.schedule_task(task)
        return jsonify(serialize_task(task)), HTTPStatus.CREATED

    @app.get("/tasks")
    def list_tasks():
        status = request.args.get("status")
        if status and status not in TaskStatus.values():
            raise ValidationError(
                f"status must be one of: {', '.join(TaskStatus.values())}"
            )

        tasks = repository.list_tasks(status=status)
        return jsonify([serialize_task(task) for task in tasks]), HTTPStatus.OK

    @app.get("/tasks/<task_id>")
    def get_task(task_id: str):
        task = repository.get_task(task_id)
        if task is None:
            return _error("not_found", "Task not found.", HTTPStatus.NOT_FOUND)
        return jsonify(serialize_task(task)), HTTPStatus.OK

    @app.patch("/tasks/<task_id>")
    def update_task(task_id: str):
        existing_task = repository.get_task(task_id)
        if existing_task is None:
            return _error("not_found", "Task not found.", HTTPStatus.NOT_FOUND)
        if existing_task.status != TaskStatus.PENDING.value:
            return _error(
                "task_not_pending",
                "Only pending tasks can be updated.",
                HTTPStatus.CONFLICT,
            )

        payload = _json_payload()
        has_schedule_time = "schedule_time" in payload
        has_lines = "lines" in payload
        if not has_schedule_time and not has_lines:
            raise ValidationError("Provide schedule_time and/or lines to update.")

        schedule_time = (
            extract_schedule_time(payload, default_to_now=True)
            if has_schedule_time
            else None
        )
        lines = parse_lines(payload.get("lines"), required=False) if has_lines else None

        updated_task = repository.update_pending_task(
            task_id=task_id,
            schedule_time=schedule_time,
            lines=lines,
        )
        task_scheduler.reschedule_task(updated_task)
        return jsonify(serialize_task(updated_task)), HTTPStatus.OK

    @app.delete("/tasks/<task_id>")
    def delete_task(task_id: str):
        task = repository.get_task(task_id)
        if task is None:
            return _error("not_found", "Task not found.", HTTPStatus.NOT_FOUND)
        if task.status == TaskStatus.RUNNING.value:
            return _error(
                "task_running",
                "Running tasks cannot be deleted.",
                HTTPStatus.CONFLICT,
            )

        if task.status == TaskStatus.PENDING.value:
            task_scheduler.unschedule_task(task_id)
        repository.delete_task(task_id)
        return "", HTTPStatus.NO_CONTENT


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError):
        return _error("validation_error", str(error), HTTPStatus.BAD_REQUEST)

    @app.errorhandler(404)
    def handle_missing_route(_error_value):
        return _error("not_found", "Route not found.", HTTPStatus.NOT_FOUND)

    @app.errorhandler(TaskNotFoundError)
    def handle_task_not_found(_error_value):
        return _error("not_found", "Task not found.", HTTPStatus.NOT_FOUND)

    @app.errorhandler(TaskStateError)
    def handle_task_state_error(error: TaskStateError):
        return _error("task_not_pending", str(error), HTTPStatus.CONFLICT)


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object.")
    return payload


def _error(code: str, message: str, status: HTTPStatus):
    return jsonify({"error": {"code": code, "message": message}}), status


if __name__ == "__main__":
    application = create_app()
    application.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5555")),
    )
