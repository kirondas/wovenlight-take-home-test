from http import HTTPStatus
from typing import Any

from flask import Blueprint, jsonify, request

from wovenlight_scheduler.domain import ValidationError
from wovenlight_scheduler.service import TaskAlreadyExecutedError, TaskNotFoundError, TaskService


def create_tasks_blueprint(service: TaskService) -> Blueprint:
    blueprint = Blueprint("tasks", __name__)

    @blueprint.post("/tasks")
    def create_task() -> tuple[Any, int]:
        task = service.create_task(_json_payload())
        return jsonify(task.to_dict()), HTTPStatus.CREATED

    @blueprint.get("/tasks")
    def list_tasks() -> Any:
        return jsonify([task.to_dict() for task in service.list_tasks()])

    @blueprint.get("/tasks/<task_id>")
    def get_task(task_id: str) -> Any:
        return jsonify(service.get_task(task_id).to_dict())

    @blueprint.patch("/tasks/<task_id>")
    def update_task(task_id: str) -> Any:
        return jsonify(service.update_task(task_id, _json_payload()).to_dict())

    @blueprint.delete("/tasks/<task_id>")
    def delete_task(task_id: str) -> tuple[str, int]:
        service.delete_task(task_id)
        return "", HTTPStatus.NO_CONTENT

    return blueprint


def register_error_handlers(app: Any) -> None:
    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError) -> tuple[Any, int]:
        return jsonify({"error": str(error)}), HTTPStatus.BAD_REQUEST

    @app.errorhandler(TaskNotFoundError)
    def handle_not_found(_: TaskNotFoundError) -> tuple[Any, int]:
        return jsonify({"error": "Task not found"}), HTTPStatus.NOT_FOUND

    @app.errorhandler(TaskAlreadyExecutedError)
    def handle_conflict(error: TaskAlreadyExecutedError) -> tuple[Any, int]:
        return jsonify({"error": str(error)}), HTTPStatus.CONFLICT


def _json_payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object")
    return payload
