import uuid

from tfl_scheduler.models import TaskStatus

from .conftest import future_time


def _assert_validation_error(response):
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


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


# Invalid requests: POST /tasks


def test_create_task_rejects_missing_lines(client):
    response = client.post("/tasks", json={"schedule_time": future_time()})
    _assert_validation_error(response)


def test_create_task_rejects_empty_lines_string(client):
    response = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": ""},
    )
    _assert_validation_error(response)


def test_create_task_rejects_whitespace_only_lines(client):
    response = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": " , , "},
    )
    _assert_validation_error(response)


def test_create_task_rejects_lines_as_list_instead_of_string(client):
    response = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": ["victoria", "central"]},
    )
    _assert_validation_error(response)


def test_create_task_rejects_malformed_schedule_time(client):
    response = client.post(
        "/tasks",
        json={"schedule_time": "2099/01/01 17:00:00", "lines": "victoria"},
    )
    _assert_validation_error(response)


def test_create_task_rejects_non_string_schedule_time(client):
    response = client.post(
        "/tasks",
        json={"schedule_time": 20990101, "lines": "victoria"},
    )
    _assert_validation_error(response)


def test_create_task_rejects_conflicting_schedule_and_scheduler_fields(client):
    response = client.post(
        "/tasks",
        json={
            "schedule_time": future_time(),
            "scheduler_time": "2099-02-02T12:00:00",
            "lines": "victoria",
        },
    )
    _assert_validation_error(response)


def test_create_task_accepts_matching_schedule_and_scheduler_fields(client):
    """Both keys may appear only if values match (backward compatibility edge case)."""
    t = future_time()
    response = client.post(
        "/tasks",
        json={
            "schedule_time": t,
            "scheduler_time": t,
            "lines": "victoria",
        },
    )
    assert response.status_code == 201


def test_create_task_rejects_non_object_json_body(client):
    response = client.post("/tasks", json=["not", "an", "object"])
    _assert_validation_error(response)


def test_create_task_rejects_invalid_json_body(client):
    response = client.post(
        "/tasks",
        data="{not-valid-json",
        content_type="application/json",
    )
    _assert_validation_error(response)


def test_create_task_rejects_plain_text_body(client):
    response = client.post(
        "/tasks",
        data="schedule_time=2099-01-01T17:00:00",
        content_type="text/plain",
    )
    _assert_validation_error(response)


# Invalid requests: GET


def test_get_task_returns_404_for_unknown_id(client):
    unknown = str(uuid.uuid4())
    response = client.get(f"/tasks/{unknown}")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_list_tasks_rejects_invalid_status_filter(client):
    response = client.get("/tasks?status=done")
    _assert_validation_error(response)


# Invalid requests: PATCH


def test_patch_task_returns_404_for_unknown_id(client):
    unknown = str(uuid.uuid4())
    response = client.patch(
        f"/tasks/{unknown}",
        json={"lines": "victoria"},
    )
    assert response.status_code == 404


def test_patch_pending_task_rejects_empty_body(client):
    created = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "jubilee"},
    ).get_json()

    response = client.patch(f"/tasks/{created['id']}", json={})
    _assert_validation_error(response)


def test_patch_pending_task_rejects_invalid_lines(client):
    created = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "jubilee"},
    ).get_json()

    response = client.patch(
        f"/tasks/{created['id']}",
        json={"lines": "not-a-line"},
    )
    _assert_validation_error(response)


def test_patch_pending_task_rejects_conflicting_schedule_fields(client):
    created = client.post(
        "/tasks",
        json={"schedule_time": future_time(), "lines": "jubilee"},
    ).get_json()

    response = client.patch(
        f"/tasks/{created['id']}",
        json={
            "schedule_time": "2099-03-03T10:00:00",
            "scheduler_time": "2099-03-03T11:00:00",
        },
    )
    _assert_validation_error(response)


# Invalid requests: DELETE


def test_delete_task_returns_404_for_unknown_id(client):
    unknown = str(uuid.uuid4())
    response = client.delete(f"/tasks/{unknown}")
    assert response.status_code == 404
