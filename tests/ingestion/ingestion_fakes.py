"""In-memory collaborators shared by the OC-004 ingestion tests."""

from app.core.interfaces.repositories import AbstractUnitOfWork


def valid_poi(i, district="quan 1", city="ho chi minh", address="default"):
    if address == "default":
        address = {"district": district, "city": city}
    return {
        "id": f"poi_{i}",
        "name": f"POI {i}",
        "longitude": 106.7 + i * 0.001,
        "latitude": 10.7 + i * 0.001,
        "address": address,
    }


class FakePOIRepository:
    """Records accepted chunks; can be told to fail forever or by id.

    ``build_nearby_edges_for_poi`` is the spatial contract used by the
    post-write spatial stage (OC-017). It records every rebuilt id/radius and can
    be told to fail (all or by id) so the accounting-vs-spatial separation can be
    asserted.
    """

    def __init__(
        self,
        fail_times=0,
        fail_forever=False,
        fail_ids=None,
        spatial_fail_ids=None,
        spatial_fail_forever=False,
        spatial_error=None,
    ):
        self.rows = []
        self.calls = 0
        self.fail_times = fail_times
        self.fail_forever = fail_forever
        self.fail_ids = set(fail_ids or [])
        self.spatial_calls = []
        self.spatial_fail_ids = set(spatial_fail_ids or [])
        self.spatial_fail_forever = spatial_fail_forever
        self.spatial_error = spatial_error

    def batch_create(self, chunk):
        self.calls += 1
        if self.fail_forever:
            raise RuntimeError("simulated graph outage")
        if any(p.get("id") in self.fail_ids for p in chunk):
            raise RuntimeError("simulated graph outage")
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("simulated graph outage")
        self.rows.extend(chunk)
        return len(chunk)

    def build_nearby_edges_for_poi(self, poi_id, radius_km=3.0):
        self.spatial_calls.append((poi_id, radius_km))
        if self.spatial_error is not None:
            raise self.spatial_error
        if self.spatial_fail_forever or poi_id in self.spatial_fail_ids:
            raise RuntimeError("simulated spatial outage")
        return 1



class FakeUnitOfWork(AbstractUnitOfWork):
    def __init__(self, repo):
        self.pois = repo
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class UoWFactory:
    def __init__(self, repo):
        self.repo = repo
        self.uows = []

    def __call__(self):
        uow = FakeUnitOfWork(self.repo)
        self.uows.append(uow)
        return uow


class FailingCanaryService:
    """Stand-in service whose synchronous canary raises an unexpected error."""

    def __init__(self):
        self.called = False

    def process_canary_and_split(self, payload, limit=10):
        self.called = True
        raise RuntimeError("boom: sensitive internal detail")

    async def process_background_remainder(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("background must not run after an unexpected canary error")

    async def finalize_canary_job(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("terminal must not run after an unexpected canary error")
