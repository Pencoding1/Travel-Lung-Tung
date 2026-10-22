"""The spatial updater must report per-district outcomes honestly.

``tenacity`` is a production dependency of ``updater.py`` but is not installed
in every validation virtualenv. This module skips cleanly when it is absent
(and is executed in the env that does provide it), so no package is installed.
"""

import json

import pytest

pytest.importorskip("tenacity")

from tenacity import wait_none  # noqa: E402

from app.core.utils.updater import SpatialUpdater  # noqa: E402


def test_report_is_honest_about_failed_district():
    updater = SpatialUpdater()

    def fake_build(district_id, uow_factory):
        if district_id == "bad":
            raise RuntimeError("raw provider secret text")
        return 7

    updater._build_district_with_retry = fake_build

    report = updater._execute_update(["good", "bad"], uow_factory=None)

    assert report["is_success"] is False
    assert report["succeeded"] == {"good": 7}
    assert report["failed"] == {"bad": "RuntimeError"}
    assert report["total_edges"] == 7
    # Sanitized: the raw exception text never reaches the report.
    assert "raw provider secret text" not in json.dumps(report)


def test_report_success_only_when_every_district_succeeds():
    updater = SpatialUpdater()
    updater._build_district_with_retry = lambda district_id, factory: 3

    report = updater._execute_update(["d1", "d2"], uow_factory=None)

    assert report["is_success"] is True
    assert report["succeeded"] == {"d1": 3, "d2": 3}
    assert report["failed"] == {}
    assert report["total_edges"] == 6


def test_retry_uses_a_fresh_uow_per_attempt():
    original_wait = SpatialUpdater._build_district_with_retry.retry.wait
    SpatialUpdater._build_district_with_retry.retry.wait = wait_none()

    calls = {"builds": 0, "factories": 0}

    class Repo:
        def build_nearby_edges_for_district(self, district_id, radius_km):
            calls["builds"] += 1
            if calls["builds"] == 1:
                raise RuntimeError("transient failure")
            return 4

    class Uow:
        def __init__(self):
            self.pois = Repo()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, tb):
            return False

    def factory():
        calls["factories"] += 1
        return Uow()

    try:
        edges = SpatialUpdater()._build_district_with_retry("d1", factory)
    finally:
        SpatialUpdater._build_district_with_retry.retry.wait = original_wait

    assert edges == 4
    assert calls["factories"] == 2  # a fresh UnitOfWork for every attempt
    assert calls["builds"] == 2


def test_trigger_update_sync_returns_report_without_background_tasks():
    updater = SpatialUpdater()
    updater._build_district_with_retry = lambda district_id, factory: 2

    report = updater.trigger_update(["d1"], uow_factory=None, background_tasks=None)

    assert report is not None
    assert report["is_success"] is True
    assert report["succeeded"] == {"d1": 2}
