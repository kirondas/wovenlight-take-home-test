from tfl_scheduler.models import TaskStatus

from .conftest import future_time


def test_create_task_accepts_schedule_time(client):
    response = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "victoria,central"},
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["status"] == TaskStatus.PENDING.value
    assert body["lines"] == "victoria,central"
    assert body["result"] is None


def test_create_task_accepts_scheduler_time_alias(client):
    response = client.post(
        "/tasks",
        json={"scheduler_time": future_time(), "lines": "victoria"},
    )

    assert response.status_code == 201
    assert response.get_json()["lines"] == "victoria"


def test_create_task_rejects_unknown_line(client):
    response = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "not-a-line"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


def test_list_and_get_tasks(client):
    created = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "jubilee"},
    ).get_json()

    list_response = client.get("/tasks")
    get_response = client.get(f"/tasks/{created['id']}")

    assert list_response.status_code == 200
    assert len(list_response.get_json()) == 1
    assert get_response.status_code == 200
    assert get_response.get_json()["id"] == created["id"]


def test_patch_pending_task(client):
    created = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "jubilee"},
    ).get_json()

    response = client.patch(
        f"/tasks/{created['id']}",
        json={"schedule_time": "2099-01-01T18:30:00", "lines": "victoria"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["schedule_time"] == "2099-01-01T18:30:00"
    assert body["lines"] == "victoria"


def test_patch_completed_task_returns_conflict(client, repository):
    created = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "jubilee"},
    ).get_json()
    repository.mark_running(created["id"])
    repository.mark_succeeded(created["id"], [{"description": "ok"}])

    response = client.patch(
        f"/tasks/{created['id']}",
        json={"lines": "victoria"},
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "task_not_pending"


def test_delete_task(client):
    created = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "northern"},
    ).get_json()

    delete_response = client.delete(f"/tasks/{created['id']}")
    get_response = client.get(f"/tasks/{created['id']}")

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


def test_delete_running_task_returns_conflict(client, repository):
    created = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "northern"},
    ).get_json()
    repository.mark_running(created["id"])

    response = client.delete(f"/tasks/{created['id']}")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "task_running"


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
