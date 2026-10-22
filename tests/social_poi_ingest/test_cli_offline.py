"""Offline replay, CLI and policy-gate tests (fake transport; no network)."""

import json
from pathlib import Path

import pytest

from crawler_service.app.social_ingest import cli
from crawler_service.app.social_ingest.runner import RunnerError, collect_profile

from helpers import (
    FakeTransport,
    fetcher_for,
    html_response,
    synthetic_profile,
)

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


def live_result(tmp_path, *, robots_status=200, robots_body=ROBOTS):
    profile = synthetic_profile()
    transport = FakeTransport(
        {
            "https://example.test/robots.txt": html_response(
                robots_body, status=robots_status, content_type="text/plain"
            ),
            "https://example.test/pois": html_response(PAGE),
        }
    )
    result = collect_profile(
        profile, tmp_path / "out", fetcher=fetcher_for(transport)
    )
    return profile, transport, result


def test_offline_replay_is_deterministic_and_hash_verified(tmp_path):
    profile, transport, live = live_result(tmp_path)
    assert live.report["counts"]["content_pages"] == 1
    assert live.report["counts"]["extracted_records"] == 2
    assert live.report["counts"]["minimum_valid"] == 2
    assert live.report["counts"]["imported"] == 0
    first_export = live.export_path.read_bytes()

    offline = collect_profile(
        profile, tmp_path / "out", capture_index=live.index_path
    )
    assert offline.export_path.read_bytes() == first_export
    assert offline.report["mode"] == "offline_replay"
    assert offline.report["counts"] == live.report["counts"]

    raw_file = next(path for path in (tmp_path / "out" / "raw").iterdir())
    raw_file.write_bytes(raw_file.read_bytes() + b"tampered")
    with pytest.raises(RunnerError) as exc:
        collect_profile(profile, tmp_path / "out", capture_index=live.index_path)
    assert exc.value.reason == "capture_hash_mismatch"


def test_cli_offline_twice_reports_identical_counts(tmp_path, monkeypatch, capsys):
    profile, _, live = live_result(tmp_path)
    monkeypatch.setattr(cli, "get_profile", lambda name: profile)
    out = tmp_path / "out"
    for _ in range(2):
        code = cli.main(
            [
                "crawl",
                "--profile",
                profile.name,
                "--out",
                str(out),
                "--capture-index",
                str(live.index_path),
            ]
        )
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["counts"]["exported_records"] == 2
        assert payload["counts"]["imported"] == 0
        assert payload["mode"] == "offline_replay"


def test_cli_requires_exactly_one_input_mode(tmp_path, monkeypatch, capsys):
    profile = synthetic_profile()
    monkeypatch.setattr(cli, "get_profile", lambda name: profile)
    code = cli.main(["crawl", "--profile", profile.name, "--out", str(tmp_path / "out")])
    assert code == 2
    assert "exactly one input mode" in capsys.readouterr().err


def test_robots_disallow_blocks_content_fetch(tmp_path):
    profile = synthetic_profile(start_urls=("https://example.test/private/page",))
    transport = FakeTransport(
        {
            "https://example.test/robots.txt": html_response(
                ROBOTS, content_type="text/plain"
            ),
        }
    )
    with pytest.raises(RunnerError) as exc:
        collect_profile(profile, tmp_path / "out", fetcher=fetcher_for(transport))
    assert exc.value.reason == "robots_disallowed"
    assert "https://example.test/private/page" not in transport.calls


def test_unreachable_robots_is_not_permission(tmp_path):
    profile = synthetic_profile()
    transport = FakeTransport(
        {
            "https://example.test/robots.txt": html_response(
                "blocked", status=403, content_type="text/plain"
            ),
            "https://example.test/pois": html_response(PAGE),
        }
    )
    with pytest.raises(RunnerError) as exc:
        collect_profile(profile, tmp_path / "out", fetcher=fetcher_for(transport))
    assert exc.value.reason == "robots_unavailable"
    assert transport.calls == ["https://example.test/robots.txt"]


def test_403_content_page_is_reported_without_browser_fallback(tmp_path):
    profile = synthetic_profile()
    transport = FakeTransport(
        {
            "https://example.test/robots.txt": html_response(ROBOTS, content_type="text/plain"),
            "https://example.test/pois": html_response("denied", status=403),
        }
    )
    with pytest.raises(RunnerError) as exc:
        collect_profile(profile, tmp_path / "out", fetcher=fetcher_for(transport))
    assert exc.value.reason == "no_content_captures"
    assert "http_403" in exc.value.detail
