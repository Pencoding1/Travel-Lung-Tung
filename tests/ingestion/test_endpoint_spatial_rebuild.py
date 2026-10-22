"""OC-017 runtime HTTP tests for the manual spatial-rebuild endpoint.

The real FastAPI APIRouter runs in-process via Starlette's ``TestClient`` with a
synthetic JWT secret. The district rebuild is a *fake provider*: the real
``SpatialUpdater`` runs, but its per-district build is monkeypatched so no graph
or network call is made. Evidence is labelled accordingly (fake provider, real
endpoint/auth/report logic).
"""

import os
import time

import jwt
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import app.api.rest.v1.endpoint_spatial_rebuild as endpoint_module
from app.core.utils.updater import SpatialUpdater

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")


def make_token(exp_delta=3600, sub="tester"):
    payload = {"sub": sub, "role": "admin", "exp": int(time.time()) + exp_delta}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def auth_header(**kwargs):
    return {"Authorization": f"Bearer {make_token(**kwargs)}"}


def build_app():
    app = FastAPI()
    app.include_router(endpoint_module.router)
    return app


def install_fake_build(monkeypatch, fn):
    """Replace the real per-district build (bound method signature included)."""
    monkeypatch.setattr(SpatialUpdater, "_build_district_with_retry", fn)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_missing_token_is_rejected(monkeypatch):
    install_fake_build(monkeypatch, lambda self, d, f: 1)
    with TestClient(build_app()) as client:
        response = client.post("/management/pois/spatial-rebuild", json=["d1"])
    assert response.status_code in (401, 403)


def test_invalid_token_is_rejected(monkeypatch):
    install_fake_build(monkeypatch, lambda self, d, f: 1)
    with TestClient(build_app()) as client:
        response = client.post(
            "/management/pois/spatial-rebuild",
            headers={"Authorization": "Bearer not-a-real-jwt"},
            json=["d1"],
        )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
def test_empty_district_list_is_rejected(monkeypatch):
    install_fake_build(monkeypatch, lambda self, d, f: 1)
    with TestClient(build_app()) as client:
        response = client.post(
            "/management/pois/spatial-rebuild", headers=auth_header(), json=[]
        )
    assert response.status_code == 422


def test_blank_district_is_rejected(monkeypatch):
    install_fake_build(monkeypatch, lambda self, d, f: 1)
    with TestClient(build_app()) as client:
        response = client.post(
            "/management/pois/spatial-rebuild", headers=auth_header(), json=["  "]
        )
    assert response.status_code == 422


def test_oversize_district_list_is_rejected(monkeypatch):
    install_fake_build(monkeypatch, lambda self, d, f: 1)
    oversize = [f"d{i}" for i in range(endpoint_module.MAX_DISTRICTS_PER_REBUILD + 1)]
    with TestClient(build_app()) as client:
        response = client.post(
            "/management/pois/spatial-rebuild", headers=auth_header(), json=oversize
        )
    assert response.status_code == 422


def test_duplicate_districts_are_deduplicated(monkeypatch):
    calls = []

    def fake(self, district_id, factory):
        calls.append(district_id)
        return 2

    install_fake_build(monkeypatch, fake)
    with TestClient(build_app()) as client:
        response = client.post(
            "/management/pois/spatial-rebuild",
            headers=auth_header(),
            json=["d1", "d1", " d1 "],
        )
    assert response.status_code == 200
    body = response.json()
    assert body["requested"] == 1
    assert body["deduplicated"] == 2
    assert calls == ["d1"]


# ---------------------------------------------------------------------------
# Outcome reporting
# ---------------------------------------------------------------------------
def test_all_success_returns_report(monkeypatch):
    install_fake_build(monkeypatch, lambda self, district_id, factory: 5)
    with TestClient(build_app()) as client:
        response = client.post(
            "/management/pois/spatial-rebuild", headers=auth_header(), json=["d1", "d2"]
        )
    assert response.status_code == 200
    body = response.json()
    assert body["is_success"] is True
    assert body["succeeded"] == {"d1": 5, "d2": 5}
    assert body["failed"] == {}
    assert body["requested"] == 2


def test_partial_failure_returns_207_with_terminal_report(monkeypatch):
    def fake(self, district_id, factory):
        if district_id == "bad":
            raise RuntimeError("raw provider secret text")
        return 3

    install_fake_build(monkeypatch, fake)
    with TestClient(build_app()) as client:
        response = client.post(
            "/management/pois/spatial-rebuild",
            headers=auth_header(),
            json=["good", "bad"],
        )
    assert response.status_code == 207
    body = response.json()
    assert body["is_success"] is False
    assert body["succeeded"] == {"good": 3}
    assert body["failed"] == {"bad": "RuntimeError"}
    # Sanitized: the raw provider text is never echoed.
    assert "raw provider secret text" not in response.text


def test_total_failure_returns_explicit_failed_response(monkeypatch):
    def fake(self, district_id, factory):
        raise RuntimeError("raw provider secret text")

    install_fake_build(monkeypatch, fake)
    with TestClient(build_app()) as client:
        response = client.post(
            "/management/pois/spatial-rebuild", headers=auth_header(), json=["d1"]
        )
    assert response.status_code == 502
    body = response.json()
    assert body["is_success"] is False
    assert body["failed"] == {"d1": "RuntimeError"}
    assert "raw provider secret text" not in response.text
    # Never an unconditional success.
    assert body.get("status") != "success"


def test_manual_rebuild_reports_failed_when_stored_radius_incompatible(monkeypatch):
    # The repository's fixed-radius gate rejects a uniform 5 km stored policy for
    # a 3 km application rebuild. The endpoint must return an honest failure, not
    # an unconditional success, and must not echo the provider message.
    def fake(self, district_id, factory):
        raise ValueError("stored NEAR_BY radius 5.0 incompatible with fixed 3.0 km")

    install_fake_build(monkeypatch, fake)
    with TestClient(build_app()) as client:
        response = client.post(
            "/management/pois/spatial-rebuild", headers=auth_header(), json=["d1"]
        )
    assert response.status_code == 502
    body = response.json()
    assert body["is_success"] is False
    assert body["failed"] == {"d1": "ValueError"}
    assert "5.0 incompatible" not in response.text
