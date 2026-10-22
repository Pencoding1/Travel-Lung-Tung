"""Guarded public HTTP fetching with immutable raw captures.

Safety rules implemented here (all enforced *before* a socket is opened):

* only ``http``/``https`` URLs with an explicit host in the profile allowlist;
* no credentials, no fragment-only tricks, ports limited to 80/443;
* every resolved address must be public (no loopback/private/link-local/...);
* the resolved address is **pinned**: the request dials that IP directly, so DNS
  is consulted exactly once per hop and a second (rebinding) answer can never be
  used, while TLS still verifies the certificate against the URL hostname;
* environment proxy autodetection is disabled on the pinned opener, so the dial
  goes straight to the validated address;
* every redirect hop is re-validated with the same guard;
* bodies are streamed with a hard ``max_bytes + 1`` read bound — success *and*
  error responses — and an oversized body fails with its own ``oversize`` code
  instead of being truncated silently;
* a declared source whose terms forbid reuse is refused before any request;
* bounded redirects, timeout, bytes, retries and per-host pacing.

Fetches are performed through an injectable ``transport`` so tests never touch
the network. The default transport is stdlib ``urllib`` with redirects disabled
so the guard can inspect each hop itself.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .profiles import (
    SourceProfile,
    gate_for_hosts,
    gate_for_profile,
)

USER_AGENT = "TVLT-POI-Ingest/0.1 (local research; HTTP-only; no login)"

#: Per-response body budget used by the stdlib transport when a caller does not
#: pass one (``FetchPolicy.max_bytes`` is what production uses).
DEFAULT_MAX_BYTES = 2_000_000

#: Chunk size for bounded reads. The response is never buffered beyond
#: ``max_bytes + 1`` bytes no matter how the stream honours the size hint.
_BODY_CHUNK = 64 * 1024


class FetchError(RuntimeError):
    """A bounded, classified fetch failure. ``reason`` is machine-readable."""

    def __init__(self, reason: str, url: str, detail: str = "") -> None:
        self.reason = reason
        self.url = url
        self.detail = detail
        message = f"{reason}: {url}"
        if detail:
            message += f" ({detail})"
        super().__init__(message)


class UrlRejected(FetchError):
    """Raised by the URL guard before any network access."""


class LicenseBlocked(UrlRejected):
    """Declared reuse terms forbid this source; raised before any request.

    A :class:`UrlRejected` on purpose: this is a policy refusal, not a transport
    failure, so it must never be retried or worked around.
    """


@dataclass(frozen=True)
class FetchPolicy:
    allow_hosts: Tuple[str, ...]
    timeout_seconds: float = 10.0
    max_bytes: int = 2_000_000
    max_redirects: int = 3
    retries: int = 1
    min_interval_seconds: float = 1.0
    user_agent: str = USER_AGENT

    def __post_init__(self) -> None:
        if not self.allow_hosts:
            raise ValueError("allow_hosts must not be empty")
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if self.max_redirects < 0:
            raise ValueError("max_redirects must be non-negative")


@dataclass
class TransportResponse:
    status: int
    headers: Dict[str, str]
    body: bytes


@dataclass
class Capture:
    """One successfully obtained HTTP response and its exact bytes."""

    url: str
    final_url: str
    status: int
    content_type: str
    fetched_at: str
    elapsed_ms: int
    body: bytes
    headers: Dict[str, str] = field(default_factory=dict)
    redirect_chain: List[str] = field(default_factory=list)
    attempts: int = 1

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    @property
    def bytes(self) -> int:
        return len(self.body)

    def metadata(self) -> Dict[str, object]:
        """JSON-safe capture evidence; never includes the body."""

        return {
            "url": self.url,
            "final_url": self.final_url,
            "status": self.status,
            "content_type": self.content_type,
            "fetched_at": self.fetched_at,
            "elapsed_ms": self.elapsed_ms,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "redirect_chain": list(self.redirect_chain),
            "attempts": self.attempts,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


@dataclass(frozen=True)
class ResolvedTarget:
    """A URL whose host is allowlisted and whose addresses are all public.

    ``addresses`` is the exact, already-validated set the transport may dial;
    the hostname is never resolved again after this point.
    """

    url: str
    scheme: str
    host: str
    port: int
    addresses: Tuple[str, ...]

    @property
    def pinned_ips(self) -> Tuple[str, ...]:
        return self.addresses


def resolve_public_url(
    url: str,
    allow_hosts: Sequence[str],
    *,
    resolver: Optional[Callable[[str, int], Sequence[str]]] = None,
) -> ResolvedTarget:
    """Validate a URL and return it plus the public addresses to pin.

    ``resolver(host, port)`` returns the resolved IP strings. Tests inject a
    deterministic resolver; the default uses ``socket.getaddrinfo``.
    """

    if not isinstance(url, str) or not url.strip():
        raise UrlRejected("invalid_url", str(url), "empty URL")
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UrlRejected("blocked_scheme", url, f"scheme {parsed.scheme!r}")
    if parsed.username or parsed.password:
        raise UrlRejected("blocked_credentials", url, "URL contains credentials")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise UrlRejected("invalid_url", url, "missing host")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UrlRejected("invalid_url", url, str(exc)) from exc
    if port not in (80, 443):
        raise UrlRejected("blocked_port", url, str(port))

    # An IP literal must itself be public; a hostname must resolve only to
    # public addresses (checked again for every redirect hop).
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not _is_public_address(str(literal)):
        raise UrlRejected("blocked_private_address", url, str(literal))
    if host not in {h.lower().rstrip(".") for h in allow_hosts}:
        raise UrlRejected("host_not_allowlisted", url, host)
    if literal is not None:
        addresses: Tuple[str, ...] = (str(literal),)
    else:
        if resolver is None:
            def _default_resolver(name: str, port_number: int) -> Sequence[str]:
                infos = socket.getaddrinfo(name, port_number, type=socket.SOCK_STREAM)
                return [info[4][0] for info in infos]

            resolve = _default_resolver
        else:
            resolve = resolver
        try:
            resolved = list(resolve(host, port))
        except OSError as exc:
            raise UrlRejected("dns_failure", url, str(exc)) from exc
        if not resolved:
            raise UrlRejected("dns_failure", url, "no addresses")
        for address in resolved:
            if not _is_public_address(address):
                raise UrlRejected("blocked_private_address", url, address)
        addresses = tuple(dict.fromkeys(resolved))
    return ResolvedTarget(
        url=urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, "")
        ),
        scheme=parsed.scheme,
        host=host,
        port=port,
        addresses=addresses,
    )


def validate_public_url(
    url: str,
    allow_hosts: Sequence[str],
    *,
    resolver: Optional[Callable[[str, int], Sequence[str]]] = None,
) -> str:
    """Validate a URL and return it with any fragment removed."""

    return resolve_public_url(url, allow_hosts, resolver=resolver).url


def read_bounded(stream, max_bytes: int, *, url: str = "") -> bytes:
    """Read ``stream`` under a hard ``max_bytes`` ceiling.

    At most ``max_bytes + 1`` bytes are read and at most that many are kept in
    memory; the extra probe byte only proves the limit was crossed. Callers own
    closing ``stream`` (the stdlib transport closes it before propagating).
    """

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    budget = max_bytes + 1
    chunks: List[bytes] = []
    consumed = 0
    while consumed < budget:
        chunk = stream.read(min(_BODY_CHUNK, budget - consumed))
        if not chunk:
            break
        remaining = budget - consumed
        if len(chunk) > remaining:  # stream ignored the size hint
            chunk = chunk[:remaining]
        chunks.append(chunk)
        consumed += len(chunk)
    body = b"".join(chunks)
    if len(body) > max_bytes:
        raise FetchError("oversize", url, f"streamed more than {max_bytes} bytes")
    return body


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


class _PinnedDialer:
    """Dial only pre-validated addresses; the hostname is never re-resolved.

    ``http.client`` stores ``_create_connection`` as an *instance* attribute
    ("to allow unit tests to replace it with a suitable mockup"), so overriding
    it here keeps the stock ``connect()`` — audit hook, ``TCP_NODELAY``, tunnel
    handshake — and changes only the address that gets dialled.
    """

    pinned_ips: Tuple[str, ...]

    def _dial_pinned(self, address, timeout=None, source_address=None):
        port = address[1]
        last_error: Optional[OSError] = None
        for ip in self.pinned_ips:
            try:
                return socket.create_connection((ip, port), timeout, source_address)
            except OSError as exc:
                last_error = exc
        raise last_error or OSError("no pinned address")

    def _install_pin(self, pinned_ips: Sequence[str]) -> None:
        if not pinned_ips:
            raise ValueError("pinned_ips must not be empty")
        self.pinned_ips = tuple(pinned_ips)
        self._create_connection = self._dial_pinned


class _PinnedHTTPConnection(_PinnedDialer, http.client.HTTPConnection):
    def __init__(self, host, port=None, *, pinned_ips: Sequence[str], **kwargs) -> None:
        super().__init__(host, port, **kwargs)
        self._install_pin(pinned_ips)


class _PinnedHTTPSConnection(_PinnedDialer, http.client.HTTPSConnection):
    """Pinned dial with unchanged TLS hostname verification.

    ``connect()`` is inherited: after the pinned socket is up it wraps with
    ``server_hostname=self.host`` (the URL host, never the IP), and the context
    keeps ``check_hostname=True`` / ``CERT_REQUIRED``.
    """

    def __init__(self, host, port=None, *, pinned_ips: Sequence[str], **kwargs) -> None:
        super().__init__(host, port, **kwargs)
        self._install_pin(pinned_ips)


def _connection_factory(cls, pinned_ips: Sequence[str]):
    def build(host, port=None, **kwargs):
        return cls(host, port, pinned_ips=pinned_ips, **kwargs)

    return build


class _PinnedHandler(urllib.request.HTTPHandler, urllib.request.HTTPSHandler):
    """HTTP/HTTPS handler that can only dial the validated addresses.

    It subclasses *both* stock handlers so ``build_opener`` drops the default
    ``HTTPHandler`` **and** ``HTTPSHandler``: leaving ``HTTPSHandler`` in place
    would win the https lookup and dial the hostname unpinned (and with
    environment proxies), which is exactly the gap this class closes.
    """

    def __init__(
        self,
        pinned_ips: Sequence[str],
        *,
        ssl_context: Optional[ssl.SSLContext] = None,
    ) -> None:
        super().__init__()
        self._pinned_ips = tuple(pinned_ips)
        self._ssl_context = ssl_context

    def http_open(self, req):
        return self.do_open(
            _connection_factory(_PinnedHTTPConnection, self._pinned_ips), req
        )

    def https_open(self, req):
        kwargs = {}
        if self._ssl_context is not None:
            kwargs["context"] = self._ssl_context
        return self.do_open(
            _connection_factory(_PinnedHTTPSConnection, self._pinned_ips),
            req,
            **kwargs,
        )


def build_ssl_context() -> ssl.SSLContext:
    """TLS context for pinned fetches; verification is never weakened."""

    context = ssl.create_default_context()
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise RuntimeError("refusing to fetch with weakened TLS verification")
    return context


def _build_opener(
    pinned_ips: Sequence[str], *, ssl_context: Optional[ssl.SSLContext] = None
) -> urllib.request.OpenerDirector:
    """Opener with proxy autodetection disabled and redirects not followed."""

    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
        _PinnedHandler(pinned_ips, ssl_context=ssl_context),
    )


def _reject_declared_oversize(headers: Dict[str, str], max_bytes: int, url: str) -> None:
    declared = headers.get("content-length")
    if declared is None:
        return
    try:
        declared_bytes = int(declared)
    except ValueError:
        return
    if declared_bytes > max_bytes:
        raise FetchError("oversize", url, f"declared {declared_bytes} bytes")


def _read_error_body(exc: urllib.error.HTTPError, max_bytes: int, url: str) -> bytes:
    """Bounded read of an error response; the stream is closed either way."""

    try:
        return read_bounded(exc, max_bytes, url=url)
    except FetchError as oversize:
        if oversize.reason == "oversize":
            oversize.detail = (
                f"status {int(getattr(exc, 'code', 0) or 0)}: {oversize.detail}"
            )
        raise
    finally:
        try:
            exc.close()
        except Exception:  # pragma: no cover - defensive
            pass


def default_transport(
    url: str,
    timeout: float,
    headers: Dict[str, str],
    *,
    pinned_ips: Sequence[str],
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> TransportResponse:
    """Stdlib transport pinned to addresses that were already validated.

    ``pinned_ips`` is required: there is deliberately no code path that resolves
    the hostname inside the transport, because that is exactly the rebinding
    gap. Redirects are disabled so the caller follows and re-validates each hop.
    """

    if not pinned_ips:
        raise UrlRejected("unpinned_transport", url, "no validated address to pin")
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = _build_opener(pinned_ips, ssl_context=build_ssl_context())
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        error_headers = {
            str(k).lower(): str(v) for k, v in (exc.headers or {}).items()
        }
        return TransportResponse(
            status=int(exc.code),
            headers=error_headers,
            body=_read_error_body(exc, max_bytes, url),
        )
    with response:
        status = int(getattr(response, "status", 0) or 0)
        response_headers = {
            str(k).lower(): str(v) for k, v in response.headers.items()
        }
        _reject_declared_oversize(response_headers, max_bytes, url)
        body = read_bounded(response, max_bytes, url=url)
        return TransportResponse(status=status, headers=response_headers, body=body)


class RateLimiter:
    """Per-host pacing with an injectable clock/sleep for deterministic tests."""

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._last: Dict[str, float] = {}

    def wait(self, host: str) -> None:
        if self.min_interval_seconds <= 0:
            return
        now = self._clock()
        previous = self._last.get(host)
        if previous is not None:
            remaining = self.min_interval_seconds - (now - previous)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last[host] = now


class HttpFetcher:
    """Fetch allowlisted public pages with bounded retries and redirects.

    ``profile`` binds the fetcher to a declared source so the reuse gate can
    refuse it before any request. When no profile is passed the gate is derived
    from the allowlisted hosts, so a caller that only knows the host (for
    example the CLI) still cannot fetch a source declared ``not_permitted``.
    """

    def __init__(
        self,
        policy: FetchPolicy,
        *,
        transport: Optional[Callable[[str, float, Dict[str, str]], TransportResponse]] = None,
        resolver: Optional[Callable[[str, int], Sequence[str]]] = None,
        profile: Optional[SourceProfile] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        wall_clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.policy = policy
        self._transport = transport
        self._resolver = resolver
        self._gate = (
            gate_for_profile(profile)
            if profile is not None
            else gate_for_hosts(policy.allow_hosts)
        )
        self._sleep = sleep
        self._wall_clock = wall_clock
        self._limiter = RateLimiter(
            policy.min_interval_seconds, clock=clock, sleep=sleep
        )

    @property
    def reuse_gate(self):
        """The refusal this fetcher is bound to, or ``None`` when permitted."""

        return self._gate

    def _transport_for(self, target: ResolvedTarget):
        if self._transport is not None:
            return self._transport
        return lambda url, timeout, headers: default_transport(
            url,
            timeout,
            headers,
            pinned_ips=target.pinned_ips,
            max_bytes=self.policy.max_bytes,
        )

    def _resolve(self, url: str) -> ResolvedTarget:
        """License gate first, then URL guard; both run before any socket."""

        if self._gate is not None:
            raise LicenseBlocked(
                self._gate.reason, url, self._gate.detail()
            )
        return resolve_public_url(
            url, self.policy.allow_hosts, resolver=self._resolver
        )

    def fetch(self, url: str) -> Capture:
        target = self._resolve(url)
        chain: List[str] = []
        attempts = 0
        for _hop in range(self.policy.max_redirects + 1):
            capture, attempts = self._fetch_with_retry(target, attempts)
            location = capture.headers.get("location")
            if capture.status in (301, 302, 303, 307, 308):
                if not location:
                    raise FetchError("redirect_without_location", target.url)
                if len(chain) >= self.policy.max_redirects:
                    raise FetchError(
                        "redirect_limit", url, " > ".join(chain + [target.url])
                    )
                chain.append(target.url)
                target = self._resolve(urllib.parse.urljoin(target.url, location))
                continue
            if capture.status < 200 or capture.status >= 300:
                raise FetchError(
                    f"http_{capture.status}", target.url, capture.content_type
                )
            capture.redirect_chain = chain
            capture.final_url = target.url
            return capture
        raise FetchError("redirect_limit", url, " > ".join(chain))  # pragma: no cover

    def _fetch_with_retry(
        self, target: ResolvedTarget, attempts_so_far: int
    ) -> Tuple[Capture, int]:
        url = target.url
        transport = self._transport_for(target)
        last_error: Optional[FetchError] = None
        attempts = attempts_so_far
        for attempt in range(self.policy.retries + 1):
            attempts += 1
            self._limiter.wait(target.host)
            started = time.perf_counter()
            try:
                response = transport(
                    url,
                    self.policy.timeout_seconds,
                    {"User-Agent": self.policy.user_agent, "Accept": "text/html,text/plain,text/csv,application/json;q=0.9,*/*;q=0.1"},
                )
            except TimeoutError as exc:
                last_error = FetchError("timeout", url, str(exc))
                if attempt < self.policy.retries:
                    self._sleep(min(2.0, 0.25 * (2**attempt)))
                    continue
                raise last_error from exc
            except OSError as exc:
                last_error = FetchError("network_error", url, str(exc))
                if attempt < self.policy.retries:
                    self._sleep(min(2.0, 0.25 * (2**attempt)))
                    continue
                raise last_error from exc

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            declared = response.headers.get("content-length")
            if declared is not None:
                try:
                    declared_bytes = int(declared)
                except ValueError:
                    declared_bytes = None
                if declared_bytes is not None and declared_bytes > self.policy.max_bytes:
                    raise FetchError("oversize", url, f"{declared_bytes} bytes")
            if len(response.body) > self.policy.max_bytes:
                raise FetchError("oversize", url, f"{len(response.body)} bytes")

            status = int(response.status)
            if status in (429, 500, 502, 503, 504) and attempt < self.policy.retries:
                last_error = FetchError(f"http_{status}", url, "retryable")
                self._sleep(min(2.0, 0.5 * (2**attempt)))
                continue
            headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
            return (
                Capture(
                    url=url,
                    final_url=url,
                    status=status,
                    content_type=headers.get("content-type", ""),
                    fetched_at=self._wall_clock(),
                    elapsed_ms=elapsed_ms,
                    body=response.body,
                    headers=headers,
                    attempts=attempts,
                ),
                attempts,
            )
        raise last_error or FetchError("network_error", url)  # pragma: no cover


@dataclass
class RobotsDecision:
    url: str
    status: int
    sha256: str
    allowed: bool
    reason: str
    matched_rule: Optional[str] = None

    def as_dict(self) -> Dict[str, object]:
        return {
            "url": self.url,
            "status": self.status,
            "sha256": self.sha256,
            "allowed": self.allowed,
            "reason": self.reason,
            "matched_rule": self.matched_rule,
        }


def evaluate_robots(
    capture: Capture, path: str, *, user_agent: str = "*"
) -> RobotsDecision:
    """Conservative robots evaluation for the ``*`` group.

    A missing/inaccessible robots file is **not** treated as permission by the
    caller; this function only reports what the fetched file says.
    """

    text = capture.body.decode("utf-8", errors="replace")
    groups: List[Tuple[List[str], List[Tuple[bool, str]]]] = []
    agents: List[str] = []
    rules: List[Tuple[bool, str]] = []
    saw_rule = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if saw_rule:
                groups.append((agents, rules))
                agents, rules, saw_rule = [], [], False
            agents.append(value.lower())
        elif key in ("allow", "disallow"):
            saw_rule = True
            if value:
                rules.append((key == "allow", value))
    if agents or rules:
        groups.append((agents, rules))

    applicable: List[Tuple[bool, str]] = []
    for group_agents, group_rules in groups:
        if user_agent.lower() in group_agents or "*" in group_agents:
            applicable.extend(group_rules)
    if not applicable:
        return RobotsDecision(
            capture.url, capture.status, capture.sha256, True,
            "no_matching_disallow_rule_in_minimal_parser",
        )

    # Longest matching prefix wins; Allow wins ties (standard convention).
    best: Optional[Tuple[int, bool, str]] = None
    for allow, prefix in applicable:
        if path.startswith(prefix):
            candidate = (len(prefix), allow, prefix)
            if best is None or candidate[0] > best[0] or (
                candidate[0] == best[0] and allow and not best[1]
            ):
                best = candidate
    if best is None:
        return RobotsDecision(
            capture.url, capture.status, capture.sha256, True,
            "no_matching_disallow_rule_in_minimal_parser",
        )
    return RobotsDecision(
        capture.url,
        capture.status,
        capture.sha256,
        best[1],
        "allowed_by_robots" if best[1] else "disallowed_by_robots",
        best[2],
    )
