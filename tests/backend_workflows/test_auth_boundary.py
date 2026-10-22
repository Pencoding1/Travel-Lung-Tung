"""JWT authentication-boundary tests for the draft endpoints (OC-027)."""

from __future__ import annotations

import helpers
from app.main import create_app

LIST_URL = "/api/v1/itineraries"


def _app():
    return create_app(repository=helpers.InMemoryDraftRepository())


def test_missing_secret_is_503_not_bypass(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    response = helpers.run_http(_app(), "GET", LIST_URL,
                                token=helpers.make_token())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "auth_not_configured"


def test_absent_token_is_401(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    response = helpers.run_http(_app(), "GET", LIST_URL)
    assert response.status_code == 401


def test_malformed_authorization_is_401(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    for header in ("Basic abc", "Bearer", "Bearer ", "token abc", ""):
        response = helpers.run_http(_app(), "GET", LIST_URL,
                                    headers={"Authorization": header})
        assert response.status_code == 401, header


def test_expired_token_is_401(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    token = helpers.make_token(exp_delta=-10)
    response = helpers.run_http(_app(), "GET", LIST_URL, token=token)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "token_expired"


def test_wrong_signature_is_401(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    token = helpers.make_token(secret="a-different-secret-0123456789abcdef")
    response = helpers.run_http(_app(), "GET", LIST_URL, token=token)
    assert response.status_code == 401


def test_alg_none_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    token = helpers.make_token(algorithm="none")
    response = helpers.run_http(_app(), "GET", LIST_URL, token=token)
    assert response.status_code == 401


def test_subjectless_token_is_401(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    token = helpers.make_token(include_sub=False)
    response = helpers.run_http(_app(), "GET", LIST_URL, token=token)
    assert response.status_code == 401


def test_blank_subject_is_401(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    token = helpers.make_token(sub="   ")
    response = helpers.run_http(_app(), "GET", LIST_URL, token=token)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_subject"


def test_too_long_subject_is_401(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    token = helpers.make_token(sub="u" * 600)
    response = helpers.run_http(_app(), "GET", LIST_URL, token=token)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "subject_too_long"


def test_valid_token_is_accepted(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", helpers.SECRET)
    response = helpers.run_http(_app(), "GET", LIST_URL, token=helpers.make_token())
    assert response.status_code == 200
    assert response.json()["items"] == []
