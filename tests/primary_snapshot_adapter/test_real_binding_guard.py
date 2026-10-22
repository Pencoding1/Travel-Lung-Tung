"""QA-DATA-01: the "real" snapshot label is a fixed binding, not a claim.

Before this guard, ``prepare_snapshot(base, expectations=...)`` accepted a
caller-built ``SnapshotExpectations(real=True, dataset_class=
"real_supplied_primary_snapshot", files=...)`` and returned ``plan.real = True``
for a completely different dataset (proof: hm-qa-data-01/proof/
exploit_real_label.py). The synthetic fixture path keeps working because it
declares ``real=False``.
"""

from dataclasses import replace
from pathlib import Path

import pytest
from app.core.utils.primary_snapshot import (REAL_EXPECTATIONS,
                                             SnapshotError, _validate_expectations,
                                             prepare_snapshot)


def _tampered_real_expectations():
    """A real-labelled object whose input hashes belong to other bytes."""
    files = dict(REAL_EXPECTATIONS.files)
    first = next(iter(files))
    binding = files[first]
    files[first] = replace(binding, sha256="0" * 64)
    return replace(REAL_EXPECTATIONS, files=files)


def test_caller_supplied_real_label_is_rejected():
    expectations = _tampered_real_expectations()
    assert expectations.real is True
    with pytest.raises(SnapshotError) as excinfo:
        _validate_expectations(expectations)
    assert excinfo.value.code == "real_binding_mismatch"


def test_reviewed_real_expectations_are_still_accepted():
    # The reviewed constant and an equal copy are the same binding.
    _validate_expectations(REAL_EXPECTATIONS)
    _validate_expectations(replace(REAL_EXPECTATIONS))


def test_synthetic_non_real_expectations_are_still_accepted():
    synthetic = replace(
        REAL_EXPECTATIONS,
        real=False,
        dataset_class="synthetic_fixture",
    )
    _validate_expectations(synthetic)


def test_prepare_snapshot_rejects_before_reading_any_file(tmp_path):
    # An empty directory: if the guard ran late, this would fail on the first
    # missing input file instead of on the provenance claim.
    with pytest.raises(SnapshotError) as excinfo:
        prepare_snapshot(Path(tmp_path), _tampered_real_expectations())
    assert excinfo.value.code == "real_binding_mismatch"
