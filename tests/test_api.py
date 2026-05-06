from datetime import datetime, timedelta

from wovenlight_scheduler.domain import TaskStatus


def future_time() -> str:
    return (datetime.now() + timedelta(hours=1)).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


def test_create_and_get_task(client, app) -> None:
    response = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "victoria,central"},
    )

    assert response.status_code == 201
    task = response.get_json()
    assert task["lines"] == "victoria,central"
    assert task["status"] == TaskStatus.PENDING.value
    assert app.extensions["test_scheduler"].scheduled == [task["id"]]

    get_response = client.get(f"/tasks/{task['id']}")
    assert get_response.status_code == 200
    assert get_response.get_json()["id"] == task["id"]


def test_accepts_scheduler_time_alias_from_task_examples(client) -> None:
    response = client.post(
        "/tasks",
        json={"scheduler_time": future_time(), "lines": "victoria"},
    )

    assert response.status_code == 201
    assert response.get_json()["lines"] == "victoria"


def test_empty_schedule_time_runs_immediately(client) -> None:
    response = client.post("/tasks", json={"schedule_time": "", "lines": "victoria"})

    assert response.status_code == 201
    assert response.get_json()["schedule_time"] <= datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def test_rejects_unknown_line_ids(client) -> None:
    response = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "victoria,elizabeth"},
    )

    assert response.status_code == 400
    assert "Unknown TfL line id" in response.get_json()["error"]


def test_updates_pending_task(client, app) -> None:
    created = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "victoria"},
    ).get_json()

    response = client.patch(
        f"/tasks/{created['id']}",
        json={"schedule_time": future_time(), "lines": "central"},
    )

    assert response.status_code == 200
    assert response.get_json()["lines"] == "central"
    assert app.extensions["test_scheduler"].cancelled == [created["id"]]


def test_rejects_update_after_task_has_run(client, app) -> None:
    created = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "victoria"},
    ).get_json()
    repository = app.extensions["task_repository"]
    repository.mark_completed(created["id"], result=[])

    response = client.patch(f"/tasks/{created['id']}", json={"lines": "central"})

    assert response.status_code == 409
    assert "Only pending tasks" in response.get_json()["error"]


def test_delete_cancels_pending_task(client, app) -> None:
    created = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "victoria"},
    ).get_json()

    response = client.delete(f"/tasks/{created['id']}")

    assert response.status_code == 204
    assert app.extensions["test_scheduler"].cancelled == [created["id"]]
    assert app.extensions["task_repository"].get(created["id"]).status is TaskStatus.CANCELLED


def test_missing_task_returns_404(client) -> None:
    response = client.get("/tasks/not-a-real-task")

    assert response.status_code == 404
    assert response.get_json()["error"] == "Task not found"
