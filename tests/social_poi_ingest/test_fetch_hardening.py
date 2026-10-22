"""T057a regression tests: bounded reads, DNS pinning, reuse-license gate.

Every transport here is a fake response object or a monkeypatched socket
function; no request leaves the process and no captured data is read.
"""

import socket
import ssl
import urllib.error
import urllib.request

import pytest

from crawler_service.app.social_ingest import cli
from crawler_service.app.social_ingest import fetch as fetch_mod
from crawler_service.app.social_ingest.fetch import (
    FetchError,
    FetchPolicy,
    HttpFetcher,
    LicenseBlocked,
    TransportResponse,
    UrlRejected,
    default_transport,
    read_bounded,
    resolve_public_url,
)
from crawler_service.app.social_ingest.profiles import (
    VIETNAM_TRAVEL_HCMC7,
    gate_for_hosts,
    gate_for_profile,
)
from crawler_service.app.social_ingest.runner import RunnerError, collect_profile

from helpers import FakeTransport, html_response, synthetic_profile

ALLOW = ("example.test",)
NOW = "2026-10-18T00:00:00Z"
PUBLIC = "93.184.216.34"


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #


class CountingStream:
    """Fake response body that records exactly how much a reader consumed."""

    def __init__(self, payload, *, honor_hint=True):
        self.payload = payload if isinstance(payload, bytes) else bytes(payload)
        self.honor_hint = honor_hint
        self.offset = 0
        self.read_sizes = []
        self.closed = False

    def read(self, size=-1):
        self.read_sizes.append(size)
        if self.honor_hint and isinstance(size, int) and size >= 0:
            chunk = self.payload[self.offset : self.offset + size]
        else:
            chunk = self.payload[self.offset :]
        self.offset += len(chunk)
        return chunk

    def close(self):
        self.closed = True


class FakeResponse:
    def __init__(self, body, *, status=200, headers=None, honor_hint=True):
        self.stream = CountingStream(body, honor_hint=honor_hint)
        self.status = status
        self.headers = dict(
            headers if headers is not None else {"content-type": "text/html"}
        )

    def read(self, size=-1):
        return self.stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    def close(self):
        self.stream.close()


class FakeOpener:
    def __init__(self, *, response=None, error=None):
        self.response = response
        self.error = error
        self.opens = []

    def open(self, request, timeout=None):
        self.opens.append(request.full_url)
        if self.error is not None:
            raise self.error
        return self.response


@pytest.fixture
def install_opener(monkeypatch):
    """Replace urllib's opener for the duration of one test (no sockets)."""

    def install(*, response=None, error=None):
        opener = FakeOpener(response=response, error=error)
        monkeypatch.setattr(
            fetch_mod.urllib.request, "build_opener", lambda *a, **k: opener
        )
        return opener

    return install


@pytest.fixture
def no_network(monkeypatch):
    """Fail loudly if anything tries to resolve or dial."""

    def fail(*args, **kwargs):
        pytest.fail("network access attempted")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(socket, "getaddrinfo", fail)


class FakeSocket:
    def setsockopt(self, *args):
        pass

    def close(self):
        pass


class RecordingSSLContext(ssl.SSLContext):
    """Real verification settings; records the server_hostname actually used."""

    def __init__(self, protocol=None):
        # The protocol is consumed by SSLContext.__new__; nothing to configure.
        self.server_names = []

    def wrap_socket(self, sock, *, server_hostname=None, **kwargs):
        self.server_names.append(server_hostname)
        return sock


def _fetcher(transport, *, profile=None, resolver=None):
    return HttpFetcher(
        FetchPolicy(
            allow_hosts=ALLOW,
            timeout_seconds=1.0,
            max_bytes=100_000,
            retries=0,
            min_interval_seconds=0.0,
        ),
        transport=transport,
        resolver=resolver if resolver is not None else (lambda host, port: [PUBLIC]),
        profile=profile,
        clock=lambda: 0.0,
        sleep=lambda seconds: None,
        wall_clock=lambda: NOW,
    )


# --------------------------------------------------------------------------- #
# 1. bounded reads (success *and* error branches)
# --------------------------------------------------------------------------- #


def test_read_bounded_reads_at_most_limit_plus_one():
    stream = CountingStream(b"x" * 10_000)

    with pytest.raises(FetchError) as exc:
        read_bounded(stream, 1_000, url="https://example.test/x")

    assert exc.value.reason == "oversize"
    assert stream.offset == 1_001
    assert max(stream.read_sizes) <= 1_001


def test_read_bounded_accepts_a_body_exactly_at_the_limit():
    stream = CountingStream(b"a" * 1_000)

    assert read_bounded(stream, 1_000) == b"a" * 1_000
    assert stream.read_sizes == [1_001, 1]


def test_read_bounded_never_trusts_the_stream_size_hint():
    stream = CountingStream(b"x" * 5_000_000, honor_hint=False)

    with pytest.raises(FetchError) as exc:
        read_bounded(stream, 1_000)

    assert exc.value.reason == "oversize"
    assert max(stream.read_sizes) <= 1_001


def test_oversize_success_response_fails_with_its_own_code_and_closes(install_opener):
    response = FakeResponse(b"x" * 5_000)
    opener = install_opener(response=response)
    fetcher = _fetcher(None)
    fetcher.policy = fetch_mod.FetchPolicy(
        allow_hosts=ALLOW, max_bytes=1_000, retries=1, min_interval_seconds=0.0
    )

    with pytest.raises(FetchError) as exc:
        fetcher.fetch("https://example.test/big")

    assert exc.value.reason == "oversize"
    assert response.stream.closed is True
    assert response.stream.offset <= 1_001
    assert opener.opens == ["https://example.test/big"]  # oversize is never retried


def test_oversize_error_response_is_bounded_and_closed(install_opener):
    stream = CountingStream(b"x" * 5_000)
    error = urllib.error.HTTPError(
        "https://example.test/missing", 404, "Not Found", {}, stream
    )
    install_opener(error=error)

    with pytest.raises(FetchError) as exc:
        default_transport(
            "https://example.test/missing",
            1.0,
            {"User-Agent": "t"},
            pinned_ips=(PUBLIC,),
            max_bytes=1_000,
        )

    assert exc.value.reason == "oversize"
    assert exc.value.detail.startswith("status 404")
    assert stream.closed is True
    assert stream.offset <= 1_001


def test_declared_content_length_blocks_before_any_read(install_opener):
    response = FakeResponse(
        b"x", headers={"content-type": "text/html", "content-length": "999999999"}
    )
    install_opener(response=response)

    with pytest.raises(FetchError) as exc:
        default_transport(
            "https://example.test/huge",
            1.0,
            {"User-Agent": "t"},
            pinned_ips=(PUBLIC,),
            max_bytes=1_000,
        )

    assert exc.value.reason == "oversize"
    assert response.stream.read_sizes == []
    assert response.stream.closed is True


def test_error_response_within_limit_is_returned_and_closed(install_opener):
    stream = CountingStream(b"denied")
    error = urllib.error.HTTPError(
        "https://example.test/x", 403, "Forbidden", {"content-type": "text/plain"}, stream
    )
    install_opener(error=error)

    response = default_transport(
        "https://example.test/x",
        1.0,
        {"User-Agent": "t"},
        pinned_ips=(PUBLIC,),
        max_bytes=1_000,
    )

    assert (response.status, response.body) == (403, b"denied")
    assert stream.closed is True


def test_normal_response_is_bounded_and_closed(install_opener):
    response = FakeResponse(b"hello", status=200)
    install_opener(response=response)

    result = default_transport(
        "https://example.test/x",
        1.0,
        {"User-Agent": "t"},
        pinned_ips=(PUBLIC,),
        max_bytes=1_000,
    )

    assert (result.status, result.body) == (200, b"hello")
    assert response.stream.closed is True


def test_transport_refuses_to_run_without_a_validated_address():
    with pytest.raises(UrlRejected) as exc:
        default_transport(
            "https://example.test/x", 1.0, {"User-Agent": "t"}, pinned_ips=()
        )

    assert exc.value.reason == "unpinned_transport"


# --------------------------------------------------------------------------- #
# 2. DNS pinning / rebinding / proxy
# --------------------------------------------------------------------------- #


def test_all_resolved_public_addresses_are_pinned():
    target = resolve_public_url(
        "https://example.test/x#fragment",
        ALLOW,
        resolver=lambda host, port: [PUBLIC, PUBLIC, "93.184.216.35"],
    )

    assert target.addresses == (PUBLIC, "93.184.216.35")
    assert target.port == 443
    assert target.url == "https://example.test/x"


def test_one_private_answer_blocks_the_whole_host():
    with pytest.raises(UrlRejected) as exc:
        resolve_public_url(
            "https://example.test/x",
            ALLOW,
            resolver=lambda host, port: [PUBLIC, "192.168.1.10"],
        )

    assert exc.value.reason == "blocked_private_address"


def test_resolved_address_is_pinned_and_never_resolved_twice(monkeypatch):
    # First answer is public, second would be internal: with pinning the second
    # lookup must never happen, so DNS rebinding cannot reach a private target.
    answers = [[PUBLIC], ["192.168.1.10"]]
    resolve_calls = []
    dialed = []

    def resolver(host, port):
        resolve_calls.append((host, port))
        return answers[min(len(resolve_calls) - 1, 1)]

    def fake_dial(address, timeout=None, source_address=None):
        dialed.append(address)
        raise OSError("test: outbound dial blocked")

    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: pytest.fail("second DNS resolution")
    )
    monkeypatch.setattr(socket, "create_connection", fake_dial)

    fetcher = _fetcher(None, resolver=resolver)

    with pytest.raises(FetchError) as exc:
        fetcher.fetch("https://example.test/x")

    assert exc.value.reason == "network_error"
    assert resolve_calls == [("example.test", 443)]
    assert dialed == [(PUBLIC, 443)]


def test_pinned_dial_falls_back_across_validated_addresses(monkeypatch):
    attempts = []

    def fake_dial(address, timeout=None, source_address=None):
        attempts.append(address)
        if address[0] == PUBLIC:
            raise OSError("first address down")
        return FakeSocket()

    monkeypatch.setattr(socket, "create_connection", fake_dial)

    connection = fetch_mod._PinnedHTTPConnection(
        "example.test", 80, pinned_ips=(PUBLIC, "93.184.216.35")
    )
    connection.connect()

    assert attempts == [(PUBLIC, 80), ("93.184.216.35", 80)]


def test_tls_verifies_the_url_hostname_not_the_pinned_ip(monkeypatch):
    dialed = []

    def fake_dial(address, timeout=None, source_address=None):
        dialed.append(address)
        return FakeSocket()

    monkeypatch.setattr(socket, "create_connection", fake_dial)
    context = RecordingSSLContext(ssl.PROTOCOL_TLS_CLIENT)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED

    connection = fetch_mod._PinnedHTTPSConnection(
        "example.test", 443, pinned_ips=(PUBLIC,), context=context
    )
    connection.connect()

    assert dialed == [(PUBLIC, 443)]
    assert context.server_names == ["example.test"]


def test_tls_context_is_never_weakened():
    context = fetch_mod.build_ssl_context()

    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


def _registered(opener, cls):
    return [
        handler
        for handlers in opener.handle_open.values()
        for handler in handlers
        if isinstance(handler, cls)
    ]


def test_pinned_handler_replaces_both_stock_http_handlers():
    # Regression: a pinned handler that only subclassed HTTPHandler left the
    # default HTTPSHandler registered, so https escaped pinning and proxy
    # autodetection entirely.
    opener = fetch_mod._build_opener((PUBLIC,))

    assert _registered(opener, fetch_mod._PinnedHandler)
    stock = [
        handler
        for handler in _registered(opener, urllib.request.HTTPHandler)
        if not isinstance(handler, fetch_mod._PinnedHandler)
    ] + [
        handler
        for handler in _registered(opener, urllib.request.HTTPSHandler)
        if not isinstance(handler, fetch_mod._PinnedHandler)
    ]
    assert stock == []


def test_proxy_autodetection_is_disabled_on_the_pinned_opener():
    # Passing ProxyHandler({}) makes build_opener skip the environment-reading
    # default; an empty ProxyHandler registers no open handler of its own, so no
    # proxy path survives on this opener.
    opener = fetch_mod._build_opener((PUBLIC,))

    assert _registered(opener, urllib.request.ProxyHandler) == []


def test_redirect_hop_is_resolved_and_pinned_again():
    transport = FakeTransport(
        {
            "https://example.test/start": TransportResponse(
                302, {"location": "https://example.test/next"}, b""
            ),
            "https://example.test/next": html_response("ok"),
        }
    )
    resolve_calls = []

    def resolver(host, port):
        resolve_calls.append((host, port))
        return [PUBLIC]

    capture = _fetcher(transport, resolver=resolver).fetch(
        "https://example.test/start"
    )

    assert capture.final_url == "https://example.test/next"
    assert len(resolve_calls) == 2


# --------------------------------------------------------------------------- #
# 3. reuse-license gate (before any request)
# --------------------------------------------------------------------------- #


def test_declared_non_reusable_source_sends_no_request(no_network):
    sent = []

    def transport(url, timeout, headers):
        sent.append(url)
        return TransportResponse(200, {"content-type": "text/html"}, b"<html/>")

    fetcher = HttpFetcher(
        FetchPolicy(allow_hosts=("vietnam.travel",), min_interval_seconds=0.0),
        transport=transport,
        resolver=lambda host, port: pytest.fail("resolver must not run"),
        profile=VIETNAM_TRAVEL_HCMC7,
        clock=lambda: 0.0,
        sleep=lambda seconds: None,
        wall_clock=lambda: NOW,
    )

    with pytest.raises(LicenseBlocked) as exc:
        fetcher.fetch("https://vietnam.travel/node/137")

    assert exc.value.reason == "license_reuse_not_permitted"
    assert VIETNAM_TRAVEL_HCMC7.name in exc.value.detail
    assert isinstance(exc.value, UrlRejected)  # policy refusal, not transport
    assert sent == []


def test_host_only_fetcher_is_gated_without_the_profile(no_network):
    # cli._fetcher_for() knows only the allowlisted host; the gate must still fire.
    fetcher = cli._fetcher_for(VIETNAM_TRAVEL_HCMC7)

    assert fetcher.reuse_gate is not None
    with pytest.raises(LicenseBlocked) as exc:
        fetcher.fetch("https://vietnam.travel/node/137")

    assert exc.value.reason == "license_reuse_not_permitted"


def test_unknown_reuse_status_is_refused_with_its_own_code():
    profile = synthetic_profile(
        name="synthetic_unknown_source",
        source_id="synthetic-unknown-source",
        host="unknown.test",
        allow_hosts=("unknown.test",),
        start_urls=("https://unknown.test/pois",),
        reuse_status="unknown",
    )
    fetcher = HttpFetcher(
        FetchPolicy(allow_hosts=("unknown.test",), min_interval_seconds=0.0),
        transport=lambda *args: pytest.fail("request must not be sent"),
        resolver=lambda host, port: pytest.fail("resolver must not run"),
        profile=profile,
        clock=lambda: 0.0,
        sleep=lambda seconds: None,
    )

    with pytest.raises(LicenseBlocked) as exc:
        fetcher.fetch("https://unknown.test/pois")

    assert exc.value.reason == "license_reuse_unknown"


def test_permitted_profile_is_not_blocked():
    transport = FakeTransport(
        {"https://example.test/pois": html_response("<html>ok</html>")}
    )
    fetcher = _fetcher(transport, profile=synthetic_profile())

    capture = fetcher.fetch("https://example.test/pois")

    assert capture.status == 200
    assert capture.body == b"<html>ok</html>"
    assert transport.calls == ["https://example.test/pois"]


def test_gate_helpers_cover_declared_and_undeclared_hosts():
    assert gate_for_profile(VIETNAM_TRAVEL_HCMC7).reason == "license_reuse_not_permitted"
    assert gate_for_profile(synthetic_profile()) is None
    assert gate_for_hosts(("example.test",)) is None

    blocked = gate_for_hosts(("VIETNAM.TRAVEL.",))
    assert blocked is not None
    assert blocked.source_id == VIETNAM_TRAVEL_HCMC7.source_id
    assert blocked.reason == "license_reuse_not_permitted"


def test_runner_cannot_fetch_content_for_a_non_reusable_source(tmp_path, no_network):
    fetcher = cli._fetcher_for(VIETNAM_TRAVEL_HCMC7)

    with pytest.raises(RunnerError) as exc:
        collect_profile(VIETNAM_TRAVEL_HCMC7, tmp_path / "out", fetcher=fetcher)

    # The runner fetches policy/robots before content, so the first refusal is
    # reported there; either way no request was sent (no_network proves it).
    assert exc.value.reason in {
        "robots_unavailable",
        "license_blocked",
        "license_reuse_not_permitted",
    }
