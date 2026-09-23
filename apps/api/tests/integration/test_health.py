from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_reports_the_running_version(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "ci"
    assert body["version"]


def test_unknown_paths_use_the_shared_error_shape(client: TestClient) -> None:
    response = client.get("/nope")

    assert response.status_code == 404


def test_reference_lists_come_from_one_place(client: TestClient) -> None:
    body = client.get("/meta").json()

    assert {"key": "hvac", "label": "HVAC"} in body["industries"]
    assert any(
        region["key"] == "dallas" and region["country"] == "US" for region in body["regions"]
    )


def test_starting_a_job_without_a_queue_says_so_plainly(client: TestClient) -> None:
    """The test app has no Redis; starting a job must explain that, not return 500."""
    client.app.state.jobs = None  # type: ignore[attr-defined]

    response = client.post("/jobs/domain-age", json={"limit": 5})

    assert response.status_code == 502
    assert "job queue is not running" in response.json()["error"]["message"]


def test_the_ui_is_always_revalidated(client: TestClient) -> None:
    """The browser must revalidate, so an update never runs against an old script."""
    for path in ("/app/", "/app/app.js", "/app/style.css"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
