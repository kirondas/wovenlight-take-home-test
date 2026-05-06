import atexit
import logging
from typing import Any

from flask import Flask, jsonify

from wovenlight_scheduler.api import create_tasks_blueprint, register_error_handlers
from wovenlight_scheduler.config import Config
from wovenlight_scheduler.repository import TaskRepository
from wovenlight_scheduler.scheduler import TaskScheduler
from wovenlight_scheduler.service import TaskService
from wovenlight_scheduler.tfl_client import TflClient


def create_app(config: Config | None = None, **overrides: Any) -> Flask:
    logging.basicConfig(level=logging.INFO)
    app_config = config or Config.from_env()

    repository = overrides.get("repository") or TaskRepository(app_config.database_url)
    tfl_client = overrides.get("tfl_client") or TflClient(
        base_url=app_config.tfl_base_url,
        timeout_seconds=app_config.request_timeout_seconds,
    )
    task_scheduler = overrides.get("task_scheduler") or TaskScheduler(repository, tfl_client)
    service = TaskService(repository, task_scheduler)

    app = Flask(__name__)
    app.config["APP_CONFIG"] = app_config
    app.extensions["task_repository"] = repository
    app.extensions["task_scheduler"] = task_scheduler
    app.extensions["task_service"] = service

    app.register_blueprint(create_tasks_blueprint(service))
    register_error_handlers(app)

    @app.get("/health")
    def health() -> Any:
        return jsonify({"status": "ok"})

    if app_config.start_scheduler:
        task_scheduler.start()
        atexit.register(task_scheduler.shutdown)

    return app
