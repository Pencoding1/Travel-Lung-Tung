"""OC-004 runtime HTTP tests for the ingestion endpoint.

These run the real FastAPI APIRouter in-process via Starlette's TestClient with
a synthetic JWT secret and an overridden ingestion-service dependency backed by
in-memory collaborators. No database, external API or real credential is used.
"""

import asyncio
import json
import os
import time

import jwt
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import app.api.rest.v1.endpoint_ingestion as endpoint_module
import app.core.services.ingestion as ingestion_module
from app.api.dependencies.services import get_poi_ingestion_service
from app.core.services.ingestion import POIIngestionService
from app.core.utils.broadcaster import IngestionBroadcaster

from ingestion_fakes import (
    FailingCanaryService,
    FakePOIRepository,
    UoWFactory,
    valid_poi,
)

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")


def make_token(exp_delta=3600, sub="tester"):
    payload = {"sub": sub, "role": "admin", "exp": int(time.time()) + exp_delta}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def auth_header(**kwargs):
    return {"Authorization": f"Bearer {make_token(**kwargs)}"}


def build_app(service):
    app = FastAPI()
    app.include_router(endpoint_module.router)
    app.dependency_overrides[get_poi_ingestion_service] = lambda: service
    return app


def make_service(**repo_kwargs):
    repo = FakePOIRepository(**repo_kwargs)
    service = POIIngestionService(uow_factory=UoWFactory(repo))
    return service, repo


@pytest.fixture
def broadcaster(monkeypatch):
    b = IngestionBroadcaster()
    monkeypatch.setattr(endpoint_module, "broadcaster", b)
    monkeypatch.setattr(ingestion_module, "broadcaster", b)
    return b


def test_isolated_auth_uses_synthetic_secret_without_dotenv():
    import dotenv

    import app.core.security.auth as auth

    # conftest neutralised load_dotenv so no real .env is read.
    assert dotenv.load_dotenv() is False
    # The auth module picked up our synthetic secret, not a repository secret.
    assert auth.JWT_SECRET == os.environ["JWT_SECRET"]
    assert auth.JWT_SECRET == "oc004-isolated-test-secret-0123456789abcdef"


def read_events(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_missing_token_is_rejected(broadcaster):
    service, _ = make_service()
    with TestClient(build_app(service)) as client:
        response = client.post("/ingestion/batch", json=[valid_poi(0)])
    assert response.status_code in (401, 403)


def test_invalid_token_is_rejected(broadcaster):
    service, _ = make_service()
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/ingestion/batch",
            headers={"Authorization": "Bearer not-a-real-jwt"},
            json=[valid_poi(0)],
        )
    assert response.status_code == 401


def test_expired_token_is_rejected(broadcaster):
    service, _ = make_service()
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/ingestion/batch",
            headers=auth_header(exp_delta=-10),
            json=[valid_poi(0)],
        )
    assert response.status_code == 401


def test_valid_token_reaches_canary(broadcaster):
    service, _ = make_service()
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/ingestion/batch",
            headers=auth_header(),
            json=[valid_poi(0), valid_poi(1)],
        )
    assert response.status_code == 202
    body = response.json()
    assert body["is_success"] is True
    assert body["canary_summary"]["accepted"] == 2


# ---------------------------------------------------------------------------
# Error mapping: 422 vs 503
# ---------------------------------------------------------------------------
def test_invalid_records_return_422_without_raw_dump(broadcaster):
    service, _ = make_service()
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/ingestion/batch",
            headers=auth_header(),
            json=[
                {"id": "", "name": "", "longitude": 0.0, "latitude": 0.0},
                None,
            ],
        )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error_type"] == "unprocessable_entity"
    assert "Traceback" not in response.text
    assert "RAW_CANARY_RESULT" not in response.text


def test_database_outage_returns_503_without_exception_text(broadcaster):
    service, _ = make_service(fail_forever=True)
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/ingestion/batch", headers=auth_header(), json=[valid_poi(0)]
        )
    assert response.status_code == 503
    assert response.json()["detail"]["error_type"] == "database_unavailable"
    assert "simulated graph outage" not in response.text
    assert "Traceback" not in response.text


def test_unexpected_canary_error_is_sanitized_503(broadcaster):
    failing = FailingCanaryService()
    with TestClient(build_app(failing)) as client:
        response = client.post(
            "/ingestion/batch", headers=auth_header(), json=[valid_poi(0)]
        )
    assert response.status_code == 503
    assert response.json()["detail"]["error_type"] == "internal_error"
    assert failing.called is True
    assert "sensitive internal detail" not in response.text
    assert "Traceback" not in response.text


def test_capacity_full_returns_503_before_any_write(monkeypatch):
    b = IngestionBroadcaster(max_jobs=1)
    monkeypatch.setattr(endpoint_module, "broadcaster", b)
    monkeypatch.setattr(ingestion_module, "broadcaster", b)
    b.register("occupied")

    service, repo = make_service()
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/ingestion/batch", headers=auth_header(), json=[valid_poi(0)]
        )
    assert response.status_code == 503
    assert response.json()["detail"]["error_type"] == "broadcaster_capacity"
    assert repo.rows == [], "no canary write may happen when at capacity"


# ---------------------------------------------------------------------------
# Partial payload + streaming
# ---------------------------------------------------------------------------
def test_partial_batch_stream_reports_whole_batch(broadcaster):
    service, _ = make_service()
    records = [valid_poi(i) for i in range(12)]
    records[2] = {"id": "", "name": "", "longitude": 0.0, "latitude": 0.0}
    records[11] = None

    with TestClient(build_app(service)) as client:
        response = client.post(
            "/ingestion/batch", headers=auth_header(), json=records
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        stream = client.get(f"/ingestion/stream/{job_id}", headers=auth_header())
        assert stream.status_code == 200
        events = read_events(stream.text)

    terminal = events[-1]
    assert terminal["type"] == "complete"
    assert terminal["status"] == "partial_failure"
    assert terminal["counts"]["total_received"] == 12
    assert terminal["counts"]["accepted"] == 10
    assert terminal["failed_indices"] == [2, 11]


def test_canary_only_stream_has_terminal_event(broadcaster):
    service, _ = make_service()
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/ingestion/batch", headers=auth_header(), json=[valid_poi(0), valid_poi(1)]
        )
        job_id = response.json()["job_id"]
        stream = client.get(f"/ingestion/stream/{job_id}", headers=auth_header())
        events = read_events(stream.text)

    assert events[-1]["type"] == "complete"
    assert events[-1]["status"] == "success"
    assert events[-1]["counts"]["accepted"] == 2


def test_stream_terminal_is_replayable_for_second_subscriber(broadcaster):
    service, _ = make_service()
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/ingestion/batch", headers=auth_header(), json=[valid_poi(0)]
        )
        job_id = response.json()["job_id"]

        first = read_events(
            client.get(f"/ingestion/stream/{job_id}", headers=auth_header()).text
        )
        second = read_events(
            client.get(f"/ingestion/stream/{job_id}", headers=auth_header()).text
        )

    assert first[-1]["type"] == "complete"
    assert second[-1]["type"] == "complete"


def test_unknown_job_stream_returns_404(broadcaster):
    service, _ = make_service()
    with TestClient(build_app(service)) as client:
        response = client.get(
            "/ingestion/stream/does-not-exist", headers=auth_header()
        )
    assert response.status_code == 404


def test_stream_requires_auth(broadcaster):
    service, _ = make_service()
    with TestClient(build_app(service)) as client:
        response = client.get("/ingestion/stream/whatever")
    assert response.status_code in (401, 403)


def test_non_list_body_is_rejected(broadcaster):
    service, _ = make_service()
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/ingestion/batch", headers=auth_header(), json={"id": "not-a-list"}
        )
    assert response.status_code == 422


def test_expired_job_stream_returns_404(monkeypatch):
    clock = {"t": 0.0}
    b = IngestionBroadcaster(ttl_seconds=10.0, clock=lambda: clock["t"])
    monkeypatch.setattr(endpoint_module, "broadcaster", b)
    monkeypatch.setattr(ingestion_module, "broadcaster", b)
    b.register("expiring")
    asyncio.run(b.publish("expiring", {"type": "complete", "status": "success"}))

    clock["t"] = 100.0  # past the TTL
    service, _ = make_service()
    with TestClient(build_app(service)) as client:
        response = client.get("/ingestion/stream/expiring", headers=auth_header())
    assert response.status_code == 404
