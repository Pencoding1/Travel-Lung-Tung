"""CR-057: the source reuse gate must run at the ``collect_profile`` boundary.

The refusal has to be decided before the orchestrator does anything with an
input or an output: no policy/robots request, no content request, no offline
index read, no extraction, no output directory. ``synthetic=True`` labels test
data; it is not a reuse permission, so it must not lift the refusal.

Everything here is offline: fake transports, counting fakes, and monkeypatched
sentinels. No socket is opened and no real capture index is read.
"""

import json

import pytest

from crawler_service.app.social_ingest import runner as runner_module
from crawler_service.app.social_ingest.runner import RunnerError, collect_profile

from helpers import FakeTransport, fetcher_for, html_response, synthetic_profile

PAGE = """
<main>
  <section class="ac-chapter" id="chapter-1"><h2>Museum One</h2>
    <div class="ac-body"><p>Narrative one.</p>
      <p><strong>Address:</strong> 1 A Street, District 1</p></div></section>
  <section class="ac-chapter" id="chapter-2"><h2>Museum Two</h2>
    <div class="ac-body"><p>Narrative two.</p>
      <p><strong>Address:</strong> 2 B Street, District 3</p></div></section>
</main>
"""

ROBOTS = "User-agent: *\nDisallow: /private/\n"

#: Declared reuse status that may never pass the gate, with its refusal code.
BLOCKED_STATUSES = [
    ("not_permitted", "license_reuse_not_permitted"),
    ("unknown", "license_reuse_unknown"),
]


class CountingFetcher:
    """Fetcher that records every attempt and fails the test if one happens."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch(self, url):  # noqa: ANN001 - duck-typed fetcher
        self.calls.append(url)
        raise AssertionError(f"fetch must not happen for a refused source: {url}")


def unreviewed_profile(**overrides):
    """A profile of a host that has no reviewed entry in the declared registry."""

    values = {
        "name": "unreviewed_market_source",
        "source_id": "unreviewed-market-source",
        "host": "unlisted-source.test",
        "allow_hosts": ("unlisted-source.test",),
        "start_urls": ("https://unlisted-source.test/venues",),
        "license": "UNKNOWN",
        "reuse_status": "unknown",
    }
    values.update(overrides)
    return synthetic_profile(**values)


@pytest.mark.parametrize("status,reason", BLOCKED_STATUSES)
@pytest.mark.parametrize("synthetic", [False, True])
def test_blocked_profile_refuses_before_policy_and_content_fetch(
    tmp_path, status, reason, synthetic
):
    profile = synthetic_profile(reuse_status=status)
    fetcher = CountingFetcher()
    out = tmp_path / "out"

    with pytest.raises(RunnerError) as exc:
        collect_profile(profile, out, fetcher=fetcher, synthetic=synthetic)

    assert exc.value.reason == reason
    assert f"reuse_status={status}" in exc.value.detail
    assert exc.value.reason != "input_mode_required"
    assert fetcher.calls == []
    assert not out.exists()


@pytest.mark.parametrize("status,reason", BLOCKED_STATUSES)
def test_custom_unknown_host_profile_is_blocked(tmp_path, status, reason):
    profile = unreviewed_profile(reuse_status=status)
    fetcher = CountingFetcher()
    out = tmp_path / "out"

    with pytest.raises(RunnerError) as exc:
        collect_profile(profile, out, fetcher=fetcher)

    assert exc.value.reason == reason
    assert fetcher.calls == []
    assert not out.exists()


@pytest.mark.parametrize("status,reason", BLOCKED_STATUSES)
@pytest.mark.parametrize("synthetic", [False, True])
def test_offline_replay_refuses_before_index_read_and_extraction(
    tmp_path, monkeypatch, status, reason, synthetic
):
    profile = synthetic_profile(reuse_status=status)
    reads: list[str] = []
    extracts: list[str] = []

    def sentinel_load_capture_index(path):
        reads.append(str(path))
        raise AssertionError("offline capture index must not be read")

    def sentinel_extract(*args, **kwargs):
        extracts.append("called")
        raise AssertionError("extraction must not run")

    monkeypatch.setattr(runner_module, "load_capture_index", sentinel_load_capture_index)
    monkeypatch.setattr(runner_module, "_extract", sentinel_extract)

    capture_index = tmp_path / "capture_index.json"
    out = tmp_path / "out"

    with pytest.raises(RunnerError) as exc:
        collect_profile(
            profile, out, capture_index=capture_index, synthetic=synthetic
        )

    assert exc.value.reason == reason
    assert reads == []
    assert extracts == []
    assert not capture_index.exists()
    assert not out.exists()


@pytest.mark.parametrize(
    "both_modes",
    [True, False],
    ids=["both_modes_supplied", "no_mode_supplied"],
)
def test_invalid_input_mode_still_reports_input_mode_required(tmp_path, both_modes):
    # A refused profile proves the ordering: input-mode validation is decided
    # first, so an invalid call is reported as such, never as a licence refusal.
    profile = synthetic_profile(reuse_status="not_permitted")
    fetcher = CountingFetcher()
    capture_index = tmp_path / "capture_index.json"
    out = tmp_path / "out"

    kwargs = (
        {"fetcher": fetcher, "capture_index": capture_index} if both_modes else {}
    )

    with pytest.raises(RunnerError) as exc:
        collect_profile(profile, out, **kwargs)

    assert exc.value.reason == "input_mode_required"
    assert fetcher.calls == []
    assert not out.exists()


def test_content_budget_validation_is_still_enforced(tmp_path):
    # Preserved behaviour: a permitted profile whose budget check fails still
    # stops before any directory or fetch. ``max_content_urls`` is lowered after
    # construction because ``SourceProfile`` rejects that state up front.
    profile = synthetic_profile()
    object.__setattr__(profile, "max_content_urls", 0)
    fetcher = CountingFetcher()
    out = tmp_path / "out"

    with pytest.raises(RunnerError) as exc:
        collect_profile(profile, out, fetcher=fetcher)

    assert exc.value.reason == "content_budget_exceeded"
    assert fetcher.calls == []
    assert not out.exists()


def test_permitted_profile_still_collects_with_valid_fixture(tmp_path):
    profile = synthetic_profile()
    transport = FakeTransport(
        {
            "https://example.test/robots.txt": html_response(
                ROBOTS, content_type="text/plain"
            ),
            "https://example.test/pois": html_response(PAGE),
        }
    )
    out = tmp_path / "out"

    result = collect_profile(profile, out, fetcher=fetcher_for(transport))

    assert result.report["mode"] == "live_http"
    assert result.report["synthetic"] is False
    assert result.report["counts"]["content_pages"] == 1
    assert result.report["counts"]["extracted_records"] == 2
    assert result.report["counts"]["minimum_valid"] == 2
    assert result.report["counts"]["imported"] == 0
    assert result.report["policy"]["reuse_permitted"] is True
    assert "attribution" not in result.report["policy"]
    assert result.export_path.is_file()
    assert result.manifest_path.is_file()
    assert result.mapping_path.is_file()
    assert result.report_path.is_file()
    assert result.index_path.is_file()
    assert len(list((out / "raw").iterdir())) == 1
    export_document = json.loads(result.export_path.read_text(encoding="utf-8"))
    assert len(export_document["records"]) == 2
    assert export_document["source"]["reuse_status"] == "permitted"
