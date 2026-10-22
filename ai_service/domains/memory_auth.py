"""Authentication boundary for durable profile memory (OC-009).

This module verifies *caller-supplied* bearer tokens so that a durable profile
can be scoped to a verified subject. It performs no network I/O and never reads
``.env``; the secret is read from the process environment (``JWT_SECRET``).

Design constraints (see docs/decisions/007-chat-memory.md):

* Only HS256 is accepted. The token must carry an ``exp`` expiry and a nonblank
  string ``sub`` subject; both are required.
* A missing/blank ``JWT_SECRET`` is a *configuration* failure (HTTP 503), not an
  authentication bypass. There is deliberately no "anonymous owner" fallback for
  durable profiles.
* Any invalid, expired, wrongly-signed or subject-less token is rejected (401).
* The caller's ``user_id``/``session_id`` is never used as an owner; only the
  verified ``sub`` claim is.
"""

from __future__ import annotations

import os
from typing import Optional

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

JWT_ALGORITHM = "HS256"

# A verified ``sub`` is used verbatim as an owner key (durable profile row) and
# feeds the working-memory namespace derivation. Reject an unreasonably long
# subject explicitly at the auth boundary so a hostile credential surfaces a
# structured 401 instead of an uncaught length ``ValueError`` deeper in the
# request. The bound is generous for real identity ids and does not trim the
# subject, so its exact verified semantics are preserved.
MAX_SUBJECT_CHARS = 512


class AuthError(Exception):
    """Carries the HTTP status and a stable, non-sensitive error code."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def get_jwt_secret() -> Optional[str]:
    """Return the configured secret, or ``None`` when unset/blank."""
    secret = os.getenv("JWT_SECRET")
    if isinstance(secret, str) and secret.strip():
        return secret
    return None


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not isinstance(authorization, str):
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def decode_subject(token: str, secret: str) -> str:
    """Verify ``token`` and return its nonblank ``sub``; raise ``AuthError``."""
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except ExpiredSignatureError:
        raise AuthError(401, "token_expired", "The bearer token has expired.")
    except InvalidTokenError:
        raise AuthError(401, "invalid_token", "The bearer token is invalid.")

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise AuthError(401, "invalid_subject", "The bearer token has no subject.")
    if len(subject) > MAX_SUBJECT_CHARS:
        raise AuthError(401, "subject_too_long",
                        "The bearer token subject exceeds the supported length.")
    return subject


def verify_bearer(authorization: Optional[str]) -> str:
    """Return the verified subject for a required bearer token.

    503 when authentication is not configured, 401 when the token is absent,
    malformed, expired, wrongly-signed or subject-less.
    """
    secret = get_jwt_secret()
    if secret is None:
        raise AuthError(503, "auth_not_configured",
                        "Authentication is not configured on this service.")
    token = _extract_bearer(authorization)
    if token is None:
        raise AuthError(401, "unauthorized", "A bearer token is required.")
    return decode_subject(token, secret)


def optional_bearer(authorization: Optional[str]) -> Optional[str]:
    """Return the verified subject for an optional bearer token.

    Only a **fully absent** ``Authorization`` header means anonymous local
    scope and returns ``None``. Any *supplied* header that is not a well-formed
    ``Bearer <token>`` — a blank value, ``Basic ...``, the bare scheme, or a
    malformed/empty token — is rejected with 401 and must never be silently
    downgraded to anonymous. A well-formed token when authentication is not
    configured is a configuration failure (503).
    """
    if authorization is None:
        return None
    token = _extract_bearer(authorization)
    if token is None:
        raise AuthError(401, "invalid_authorization",
                        "The Authorization header is malformed; a Bearer token is required.")
    secret = get_jwt_secret()
    if secret is None:
        raise AuthError(503, "auth_not_configured",
                        "Authentication is not configured on this service.")
    return decode_subject(token, secret)
