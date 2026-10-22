"""Bounded, non-secret provider errors.

Every error surfaced by the CLI adapter is a :class:`ProviderError` with a small
machine-readable code and a fixed, sanitized message. Prompts, credentials,
stdout/stderr bodies and process arguments are never embedded in an error.
"""

from __future__ import annotations


class ProviderError(RuntimeError):
    """Base class for observable, bounded provider failures."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = bool(retryable)
        self.attempts: int = 0
        self.failed_attempts: int = 0


class ModelUnavailableError(ProviderError):
    """The selected model transport could not produce a usable response."""


class ProviderConfigError(ValueError):
    """Static provider configuration is invalid (process local, not global)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
