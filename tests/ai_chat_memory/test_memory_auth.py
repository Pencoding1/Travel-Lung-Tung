"""JWT auth-boundary tests (synthetic secret/token only)."""

import pytest
from domains import memory_auth
from domains.memory_auth import AuthError

from helpers_chat_memory import bearer_value, make_token

SECRET = "synthetic-test-secret"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)


def test_valid_token_returns_subject():
    token = make_token("user-42", SECRET)
    assert memory_auth.verify_bearer(bearer_value(token)) == "user-42"


def test_absent_token_is_unauthorized():
    with pytest.raises(AuthError) as exc:
        memory_auth.verify_bearer(None)
    assert exc.value.status_code == 401


def test_expired_token_is_rejected():
    token = make_token("user-42", SECRET, exp_offset=-10)
    with pytest.raises(AuthError) as exc:
        memory_auth.verify_bearer(bearer_value(token))
    assert exc.value.status_code == 401
    assert exc.value.code == "token_expired"


def test_wrong_signature_is_rejected():
    token = make_token("user-42", "other-secret")
    with pytest.raises(AuthError) as exc:
        memory_auth.verify_bearer(bearer_value(token))
    assert exc.value.status_code == 401


def test_missing_subject_is_rejected():
    token = make_token(secret=SECRET, include_sub=False)
    with pytest.raises(AuthError) as exc:
        memory_auth.verify_bearer(bearer_value(token))
    assert exc.value.status_code == 401


def test_blank_subject_is_rejected():
    token = make_token("   ", SECRET)
    with pytest.raises(AuthError) as exc:
        memory_auth.verify_bearer(bearer_value(token))
    assert exc.value.status_code == 401


def test_missing_exp_is_rejected():
    token = make_token("user-42", SECRET, include_exp=False)
    with pytest.raises(AuthError) as exc:
        memory_auth.verify_bearer(bearer_value(token))
    assert exc.value.status_code == 401


def test_missing_config_is_503(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(AuthError) as exc:
        memory_auth.verify_bearer(bearer_value(make_token("u", SECRET)))
    assert exc.value.status_code == 503


def test_optional_bearer_absent_is_none():
    assert memory_auth.optional_bearer(None) is None


def test_optional_bearer_invalid_is_rejected_not_anonymous():
    token = make_token("u", "wrong")
    with pytest.raises(AuthError) as exc:
        memory_auth.optional_bearer(bearer_value(token))
    assert exc.value.status_code == 401


def test_optional_bearer_supplied_without_config_is_503(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(AuthError) as exc:
        memory_auth.optional_bearer(bearer_value(make_token("u", SECRET)))
    assert exc.value.status_code == 503


@pytest.mark.parametrize("header", [
    "Basic invalid",
    "",
    "Bearer",
    "Bearer ",
    "   ",
    "token abc",
    "bearer",  # scheme without a token
])
def test_supplied_malformed_authorization_is_401(header):
    """Only a fully absent header may be anonymous; anything supplied must 401."""
    with pytest.raises(AuthError) as exc:
        memory_auth.optional_bearer(header)
    assert exc.value.status_code == 401


def test_supplied_malformed_authorization_without_config_is_still_401(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(AuthError) as exc:
        memory_auth.optional_bearer("Basic invalid")
    assert exc.value.status_code == 401
