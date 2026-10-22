"""JWT authentication boundary for the backend itinerary-draft workflow (OC-027).

This module verifies *caller-supplied* bearer tokens so an itinerary draft can be
scoped to a verified subject. It performs no network I/O and never reads ``.env``;
the secret is read from the process environment (``JWT_SECRET``), matching the
existing ``ai_service`` durable-memory boundary (ADR 007).

Design constraints:

* **Only HS256 is accepted.** The algorithm is pinned; a token that advertises a
  different ``alg`` (including ``none`` or an asymmetric algorithm) is rejected.
  The secret is never used with a caller-selected algorithm.
* The token must carry an ``exp`` expiry and a nonblank string ``sub`` subject;
  both are required. The subject is bounded in length and used verbatim as the
  owner key.
* A missing/blank ``JWT_SECRET`` is a *configuration* failure (HTTP 503), never an
  authentication bypass; there is deliberately no anonymous owner for drafts.
* Any absent, malformed, expired, wrongly-signed or subject-less token is a 401.
* The owner is **only** ever the verified ``sub``; a client-supplied owner field
  is never read (the request schema forbids it, see the API layer).
"""

from __future__ import annotations

import os
from typing import Optional

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

JWT_ALGORITHM = "HS256"

# A verified ``sub`` becomes the owner key of a durable draft row. Reject an
# unreasonably long subject at the boundary so a hostile credential surfaces a
# structured 401 instead of an uncaught length error deeper in a store. The bound
# is generous for real identity ids and the subject is never trimmed.
MAX_SUBJECT_CHARS = 512


class AuthError(Exception):
    """Carries an HTTP status and a stable, non-sensitive error code."""

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

    503 when authentication is not configured; 401 when the token is absent,
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
