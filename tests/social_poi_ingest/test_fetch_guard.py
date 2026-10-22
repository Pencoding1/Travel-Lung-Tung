"""Bounded-fetch guard tests (deterministic fake transport; no network)."""

import pytest

from crawler_service.app.social_ingest.fetch import (
    FetchError,
    FetchPolicy,
    HttpFetcher,
    TransportResponse,
    UrlRejected,
    evaluate_robots,
    validate_public_url,
)

from helpers import FakeTransport, fetcher_for, html_response

ALLOW = ("example.test",)


@pytest.mark.parametrize(
    "url,reason",
    [
        ("file:///etc/passwd", "blocked_scheme"),
        ("ftp://example.test/x", "blocked_scheme"),
        ("https://user:pass@example.test/x", "blocked_credentials"),
        ("https://other.test/x", "host_not_allowlisted"),
        ("https://example.test:8080/x", "blocked_port"),
        ("https://127.0.0.1/x", "blocked_private_address"),
        ("https://10.0.0.5/x", "blocked_private_address"),
        ("https://[::1]/x", "blocked_private_address"),
        ("not a url", "blocked_scheme"),
    ],
)
def test_url_guard_blocks_before_network(url, reason):
    with pytest.raises(UrlRejected) as exc:
        validate_public_url(url, ALLOW)
    assert exc.value.reason == reason


def test_url_guard_blocks_private_dns_answer():
    with pytest.raises(UrlRejected) as exc:
        validate_public_url(
            "https://example.test/x", ALLOW, resolver=lambda host, port: ["192.168.1.10"]
        )
    assert exc.value.reason == "blocked_private_address"


def test_name_resolution_failure_is_classified():
    def broken(host, port):
        raise OSError("dns down")

    with pytest.raises(UrlRejected) as exc:
        validate_public_url("https://example.test/x", ALLOW, resolver=broken)
    assert exc.value.reason == "dns_failure"


def test_redirect_to_private_or_file_is_blocked_before_following():
    transport = FakeTransport(
        {
            "https://example.test/start": TransportResponse(
                302, {"location": "file:///etc/passwd"}, b""
            )
        }
    )
    with pytest.raises(UrlRejected) as exc:
        fetcher_for(transport).fetch("https://example.test/start")
    assert exc.value.reason == "blocked_scheme"

    transport = FakeTransport(
        {
            "https://example.test/start": TransportResponse(
                302, {"location": "http://127.0.0.1/secret"}, b""
            )
        }
    )
    with pytest.raises(UrlRejected) as exc:
        fetcher_for(transport).fetch("https://example.test/start")
    assert exc.value.reason == "blocked_private_address"


def test_redirect_loop_is_bounded():
    transport = FakeTransport(
        {
            "https://example.test/a": TransportResponse(302, {"location": "/b"}, b""),
            "https://example.test/b": TransportResponse(302, {"location": "/a"}, b""),
        }
    )
    with pytest.raises(FetchError) as exc:
        fetcher_for(transport).fetch("https://example.test/a")
    assert exc.value.reason == "redirect_limit"


@pytest.mark.parametrize("status,reason", [(403, "http_403"), (429, "http_429")])
def test_403_and_429_are_reported_without_fallback(status, reason):
    transport = FakeTransport(
        {"https://example.test/x": TransportResponse(status, {}, b"blocked")}
    )
    with pytest.raises(FetchError) as exc:
        fetcher_for(transport).fetch("https://example.test/x")
    assert exc.value.reason == reason


def test_timeout_is_reported():
    transport = FakeTransport({"https://example.test/x": TimeoutError("slow")})
    with pytest.raises(FetchError) as exc:
        fetcher_for(transport).fetch("https://example.test/x")
    assert exc.value.reason == "timeout"


def test_oversize_declared_and_actual_are_rejected():
    transport = FakeTransport(
        {
            "https://example.test/declared": TransportResponse(
                200, {"content-type": "text/html", "content-length": "999999"}, b"x"
            ),
            "https://example.test/actual": TransportResponse(
                200, {"content-type": "text/html"}, b"x" * 200_000
            ),
        }
    )
    fetcher = fetcher_for(transport)
    with pytest.raises(FetchError) as exc:
        fetcher.fetch("https://example.test/declared")
    assert exc.value.reason == "oversize"
    with pytest.raises(FetchError) as exc:
        fetcher.fetch("https://example.test/actual")
    assert exc.value.reason == "oversize"


def test_success_capture_has_actual_evidence_fields():
    body = "<html>ok</html>"
    transport = FakeTransport({"https://example.test/x": html_response(body)})
    capture = fetcher_for(transport).fetch("https://example.test/x")
    assert capture.status == 200
    assert capture.bytes == len(body.encode())
    assert len(capture.sha256) == 64
    assert capture.fetched_at == "2026-10-18T00:00:00Z"
    metadata = capture.metadata()
    assert metadata["sha256"] == capture.sha256
    assert "body" not in metadata


def test_retry_succeeds_on_second_attempt_and_counts_attempts():
    class Flaky:
        def __init__(self):
            self.calls = 0

        def __call__(self, url, timeout, headers):
            self.calls += 1
            if self.calls == 1:
                return TransportResponse(503, {}, b"busy")
            return html_response("ok")

    fetcher = HttpFetcher(
        FetchPolicy(allow_hosts=ALLOW, retries=1, min_interval_seconds=0.0),
        transport=Flaky(),
        resolver=lambda host, port: ["93.184.216.34"],
        clock=lambda: 0.0,
        sleep=lambda seconds: None,
        wall_clock=lambda: "2026-10-18T00:00:00Z",
    )
    capture = fetcher.fetch("https://example.test/x")
    assert capture.attempts == 2


def test_robots_parser_disallows_matching_path():
    from crawler_service.app.social_ingest.fetch import Capture

    capture = Capture(
        url="https://example.test/robots.txt",
        final_url="https://example.test/robots.txt",
        status=200,
        content_type="text/plain",
        fetched_at="2026-10-18T00:00:00Z",
        elapsed_ms=1,
        body=b"User-agent: *\nDisallow: /search/\nDisallow: /private\n",
    )
    assert evaluate_robots(capture, "/pois").allowed is True
    assert evaluate_robots(capture, "/search/x").allowed is False
    assert evaluate_robots(capture, "/private/x").allowed is False
    assert evaluate_robots(capture, "/private").matched_rule == "/private"
