"""Typed errors for the OC-018 evaluator.

All errors are explicit and fail closed. A schema error is never silently
coerced into a default; a duplicate record key is never silently overwritten.
"""

from __future__ import annotations


class EvaluationError(Exception):
    """Base class for every evaluator failure."""


class SchemaError(EvaluationError):
    """A raw manifest or record field is missing/malformed/out of range."""


class ManifestError(EvaluationError):
    """The frozen manifest itself is internally inconsistent."""


class RecordError(EvaluationError):
    """A raw JSONL record is malformed, keyed twice or refers to unknown ids."""
