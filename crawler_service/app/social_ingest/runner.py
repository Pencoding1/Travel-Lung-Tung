"""Offline-first orchestration for one declared web source profile.

Stages and counts are explicit:

``policy check -> content fetch -> extraction -> minimum validation -> normalized
export -> acquisition manifest/mapping``

Live HTTP only happens when the caller passes a fetcher (the CLI requires an
explicit ``--fetch``). The default path re-reads an existing capture index and
verifies every raw byte hash, so repeated offline runs are deterministic and
never touch the network.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

from ..acquisition.adapters.web_poi import namespaced_entity_id
from ..acquisition.identity import sha256_bytes
from ..acquisition.storage import atomic_write_bytes, atomic_write_json
from . import SCHEMA_VERSION
from .extract import (
    ExtractionResult,
    address_hints,
    extract_csv,
    extract_html_chapters,
    extract_jsonld,
    extract_wikivoyage_listings,
    page_slug,
)
from .fetch import (
    Capture,
    FetchError,
    FetchPolicy,
    HttpFetcher,
    RobotsDecision,
    evaluate_robots,
)
from .profiles import SourceProfile, gate_for_profile, policy_allows_reuse

_MAX_REPORT_EVIDENCE = 5
_PORTABLE_STEM_LIMIT = 80
_FALLBACK_STEM = "capture"
_WINDOWS_RESERVED_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


class RunnerError(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_stem(url: str) -> str:
    path = urlsplit(url).path.strip("/") or "index"
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", path.replace("/", "_"))
    return cleaned[:80].strip("-") or "index"


def capture_extension(content_type: str) -> str:
    lowered = (content_type or "").lower()
    if "json" in lowered:
        return ".json"
    if "csv" in lowered:
        return ".csv"
    if "plain" in lowered:
        return ".txt"
    return ".html"


def write_capture(capture: Capture, directory: Path, *, stem: str) -> str:
    """Persist exact response bytes and return the relative file name.

    The stem is sanitized here, at the filesystem boundary, so a caller cannot
    escape ``directory`` or produce an unportable Windows basename. Ordinary
    stems produced by :func:`_safe_stem` already consist of portable characters
    and are kept unchanged, so previously captured file names stay stable.
    """

    directory = Path(directory)
    suffix = f"__{capture.sha256[:12]}{capture_extension(capture.content_type)}"
    portable = _portable_stem(stem)
    name = f"{portable}{suffix}"
    # Defensive only: _portable_stem already rewrites the reserved base before
    # its 80-character cap, so re-normalizing cannot push the stem over it.
    if name.split(".")[0].upper() in _WINDOWS_RESERVED_STEMS:
        portable = _portable_stem(f"capture-{portable}")
        name = f"{portable}{suffix}"
    atomic_write_bytes(directory / name, capture.body, overwrite=False)
    return f"{directory.name}/{name}"


def _portable_stem(stem: str) -> str:
    """Reduce any supplied stem to one bounded, portable Windows basename.

    ASCII letters, digits and ``._-`` are retained; every other character
    (Windows-forbidden punctuation, separators, NUL/controls, non-ASCII) becomes
    ``-``. The result is never empty, never traversal-only, has no trailing dot
    or space, is at most 80 characters, and is not a reserved device name.
    """

    text = "" if stem is None else str(stem)
    cleaned = "".join(
        char if char.isascii() and (char.isalnum() or char in "._-") else "-"
        for char in text
    )
    cleaned = cleaned.rstrip(" .")
    if not cleaned or not cleaned.strip("-._"):
        return _FALLBACK_STEM
    # Windows also treats ``CON.txt`` as the device ``CON``, so the reserved
    # check is the component before the first dot, case-insensitively, and it
    # runs *before* the length cap so an inserted prefix counts toward 80.
    if cleaned.split(".", 1)[0].upper() in _WINDOWS_RESERVED_STEMS:
        cleaned = f"capture-{cleaned}"
    cleaned = cleaned[:_PORTABLE_STEM_LIMIT].rstrip(" .")
    if not cleaned or not cleaned.strip("-._"):
        return _FALLBACK_STEM
    return cleaned



@dataclass
class CaptureIndexEntry:
    kind: str
    metadata: Dict[str, Any]
    file: str

    def as_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, **self.metadata, "file": self.file}


def _index_entries(
    captures: Dict[str, Tuple[Capture, str]], *, kind: str
) -> List[CaptureIndexEntry]:
    return [
        CaptureIndexEntry(kind=kind, metadata=capture.metadata(), file=file)
        for capture, file in captures.values()
    ]


def load_capture_index(path: Path) -> Tuple[
    Dict[str, Tuple[Capture, str]], List[CaptureIndexEntry], List[Capture]
]:
    """Load an offline index, verifying every file's exact byte hash."""

    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RunnerError("capture_index_unreadable", f"{path}: {exc}") from exc
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise RunnerError("capture_index_invalid", "missing entries array")
    captures: Dict[str, Tuple[Capture, str]] = {}
    kept: List[CaptureIndexEntry] = []
    policy_captures: List[Capture] = []
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("file"), str):
            raise RunnerError("capture_index_invalid", repr(item))
        file_path = (path.parent / item["file"]).resolve()
        try:
            body = file_path.read_bytes()
        except OSError as exc:
            raise RunnerError("capture_file_missing", f"{file_path}: {exc}") from exc
        expected = item.get("sha256")
        if not isinstance(expected, str) or sha256_bytes(body) != expected:
            raise RunnerError("capture_hash_mismatch", str(file_path))
        if int(item.get("bytes", -1)) != len(body):
            raise RunnerError("capture_size_mismatch", str(file_path))
        capture = Capture(
            url=str(item.get("url") or ""),
            final_url=str(item.get("final_url") or item.get("url") or ""),
            status=int(item.get("status") or 0),
            content_type=str(item.get("content_type") or ""),
            fetched_at=str(item.get("fetched_at") or ""),
            elapsed_ms=int(item.get("elapsed_ms") or 0),
            body=body,
            redirect_chain=list(item.get("redirect_chain") or []),
            attempts=int(item.get("attempts") or 1),
        )
        entry = CaptureIndexEntry(
            kind=str(item.get("kind") or "content"), metadata=capture.metadata(), file=item["file"]
        )
        kept.append(entry)
        if entry.kind == "content":
            captures[capture.url] = (capture, item["file"])
        elif entry.kind == "policy":
            policy_captures.append(capture)
    return captures, kept, policy_captures


def _policy_evidence(profile: SourceProfile) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for reference in profile.policy_evidence:
        path = Path(reference)
        record: Dict[str, Any] = {"reference": reference, "exists": path.is_file()}
        if path.is_file():
            payload = path.read_bytes()
            record.update(
                {"bytes": len(payload), "sha256": sha256_bytes(payload)}
            )
        evidence.append(record)
    return evidence


def _attribution(profile: SourceProfile, source_url: str) -> Optional[Dict[str, Any]]:
    """The notice that must travel with any reused text of this source.

    ``None`` for profiles whose reuse carries no attribution obligation, so the
    existing export shape of those sources is unchanged.
    """

    if not profile.attribution_required:
        return None
    return {
        "text": profile.attribution_text,
        "license": profile.license,
        "share_alike": bool(profile.share_alike),
        "source_url": source_url,
    }


def _fetch_policy_and_robots(
    profile: SourceProfile, fetcher: HttpFetcher, policy_dir: Path
) -> Tuple[List[CaptureIndexEntry], Dict[str, RobotsDecision]]:
    entries: List[CaptureIndexEntry] = []
    decisions: Dict[str, RobotsDecision] = {}
    for host in dict.fromkeys(profile.allow_hosts):
        robots_url = f"https://{host}/robots.txt"
        try:
            capture = fetcher.fetch(robots_url)
        except FetchError as exc:
            raise RunnerError(
                "robots_unavailable",
                f"{robots_url}: {exc.reason}; absent/unreachable robots is not permission",
            ) from exc
        if capture.status < 200 or capture.status >= 300:
            raise RunnerError(
                "robots_unavailable",
                f"{robots_url}: http_{capture.status}; absent/unreachable robots is not permission",
            )
        file = write_capture(capture, policy_dir, stem=f"robots-{host}")
        entries.append(
            CaptureIndexEntry(kind="policy", metadata=capture.metadata(), file=file)
        )
        decisions[host] = evaluate_robots(capture, urlsplit(profile.start_urls[0]).path)
    for host, decision in decisions.items():
        if not decision.allowed:
            raise RunnerError(
                "robots_disallowed",
                f"{host}: {decision.matched_rule}",
            )
    return entries, decisions


def _fetch_content(
    profile: SourceProfile, fetcher: HttpFetcher, raw_dir: Path
) -> Tuple[Dict[str, Tuple[Capture, str]], List[Dict[str, str]]]:
    if len(profile.start_urls) > profile.max_content_urls:
        raise RunnerError("content_budget_exceeded", profile.name)
    captures: Dict[str, Tuple[Capture, str]] = {}
    failures: List[Dict[str, str]] = []
    for url in profile.start_urls:
        try:
            capture = fetcher.fetch(url)
        except FetchError as exc:
            failures.append({"url": url, "reason": exc.reason, "detail": exc.detail})
            continue
        if "html" not in capture.content_type.lower() and profile.extractor != "csv_v1":
            failures.append(
                {"url": url, "reason": "unexpected_content_type", "detail": capture.content_type}
            )
            continue
        file = write_capture(capture, raw_dir, stem=_safe_stem(url))
        captures[url] = (capture, file)
    return captures, failures


def _extract(profile: SourceProfile, capture: Capture, file: str) -> ExtractionResult:
    if profile.extractor == "html_chapters_v1":
        return extract_html_chapters(
            capture.body.decode("utf-8", errors="replace"),
            page_url=capture.final_url,
            capture_sha256=capture.sha256,
            capture_path=file,
            fetched_at=capture.fetched_at,
            page_slug=page_slug(capture.final_url),
            category_tags=profile.category_tags,
        )
    if profile.extractor == "wikivoyage_listings_v1":
        return extract_wikivoyage_listings(
            capture.body.decode("utf-8", errors="replace"),
            page_url=capture.final_url,
            capture_sha256=capture.sha256,
            capture_path=file,
            fetched_at=capture.fetched_at,
            page_slug=page_slug(capture.final_url),
            category_tags=profile.category_tags,
        )
    if profile.extractor == "jsonld_v1":
        return extract_jsonld(
            capture.body.decode("utf-8", errors="replace"),
            page_url=capture.final_url,
            capture_sha256=capture.sha256,
            capture_path=file,
            fetched_at=capture.fetched_at,
        )
    if profile.extractor == "csv_v1":
        return extract_csv(
            capture.body,
            page_url=capture.final_url,
            capture_sha256=capture.sha256,
            capture_path=file,
            fetched_at=capture.fetched_at,
            category_tags=profile.category_tags,
        )
    raise RunnerError("unsupported_extractor", profile.extractor)


def _normalize_records(
    profile: SourceProfile, extraction: ExtractionResult
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Normalize extracted records for the ``web_poi`` export.

    Two rules are enforced here, and they must stay identical to the ones the
    ``web_poi`` acquisition adapter applies, otherwise the same record would get
    two different entities:

    * **Identity is source-namespaced.** ``record_id`` is the extractor's native
      anchor (``<page-slug>#<chapter-id>``, the JSON-LD ``@id``, the CSV
      ``id``/``url``); it is only unique inside its own page, so it is prefixed
      with the canonical URL of that page (``record.page_url``, falling back to
      the profile's start URL) before it becomes the export identity. An
      anchor that is already an absolute URL is kept verbatim -- that is what
      makes the transform idempotent when the export is re-parsed by the
      adapter. A name/address hash is never used, and the page URL alone is
      never an identity.
    * **Address is mandatory.** P0 requires name + address + (description or
      review). Coordinates never stand in for the address, so a record with
      coordinates and no address keeps ``missing_address`` and stays
      ``minimum_valid=False``; the acquisition gate then refuses to accept it.
    """

    records: List[Dict[str, Any]] = []
    counts = {
        "extracted_records": 0,
        "minimum_valid": 0,
        "missing_name": 0,
        "missing_address": 0,
        "missing_description": 0,
        "unstable_identity": 0,
    }
    namespace_fallback = profile.start_urls[0] if profile.start_urls else ""
    for record in extraction.records:
        counts["extracted_records"] += 1
        issues = list(record.issues)
        record_id = namespaced_entity_id(
            record.record_id,
            page_url=record.page_url,
            source_url=namespace_fallback,
        )
        if record.name is None and "missing_name" not in issues:
            issues.append("missing_name")
        if record.address_raw is None and "missing_address" not in issues:
            issues.append("missing_address")
        if (
            record.description is None
            and record.review_text is None
            and "missing_description" not in issues
        ):
            issues.append("missing_description")
        if not record_id and "unstable_record_anchor" not in issues:
            issues.append("unstable_record_anchor")
        if "missing_name" in issues:
            counts["missing_name"] += 1
        if "missing_address" in issues:
            counts["missing_address"] += 1
        if "missing_description" in issues:
            counts["missing_description"] += 1
        if "unstable_record_anchor" in issues:
            counts["unstable_identity"] += 1
        minimum_valid = (
            record.name is not None
            and record.address_raw is not None
            and (record.description is not None or record.review_text is not None)
        )
        if minimum_valid:
            counts["minimum_valid"] += 1
        hints = address_hints(record.address_raw)
        hints.update(record.address_hints_extra)
        normalized = {
            "record_id": record_id,
            "name": record.name,
            "address_raw": record.address_raw,
            "address_hints": hints,
            "description": record.description,
            "review_text": record.review_text,
            "category_tags": list(record.category_tags),
            "coordinates": list(record.coordinates) if record.coordinates else None,
            "opening_hours_raw": record.opening_hours_raw,
            "field_evidence": list(record.field_evidence),
            "issues": issues,
            "minimum_valid": minimum_valid,
            "page_url": record.page_url,
            "page_capture_sha256": record.page_capture_sha256,
            "page_capture_path": record.page_capture_path,
            "page_fetched_at": record.page_fetched_at,
            "locator": record.locator,
        }
        # Attribution obligation travels with the record itself (the export is
        # what a downstream consumer reuses), not only with the source block.
        record_attribution = _attribution(profile, record.page_url)
        if record_attribution is not None:
            normalized["attribution"] = record_attribution
        records.append(normalized)
    return records, counts


_ACQUISITION_CATEGORIES = [
    {"id": "attraction", "name": "Attraction", "context": "Visitor attraction candidate; category review pending"},
    {"id": "museum", "name": "Museum", "context": "Museum candidate; category review pending"},
    {"id": "cafe", "name": "Cafe", "context": "Cafe candidate; category review pending"},
    {"id": "restaurant", "name": "Restaurant", "context": "Restaurant candidate; category review pending"},
]

_DRAFT_CATEGORY_MAP = {
    "tourism=attraction": "attraction",
    "schema:touristattraction": "attraction",
    "schema:museum": "museum",
    "schema:cafeorcoffeeshop": "cafe",
    "schema:restaurant": "restaurant",
    "schema:localbusiness": "restaurant",
}


def build_mapping(
    profile: SourceProfile,
    *,
    synthetic: bool,
    entities: Optional[Dict[str, Dict[str, str]]] = None,
    categories: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Draft mapping; ``entities`` must come from an explicit reviewed fixture.

    The CLI always writes an empty ``entities`` object, so a real run cannot
    accept anything without a separate human review step.
    """

    return {
        "mapping_version": 1,
        "categories": list(categories or _ACQUISITION_CATEGORIES),
        "sources": {
            profile.source_id: {
                "synthetic": bool(synthetic),
                "districts": {},
                "category_map": dict(_DRAFT_CATEGORY_MAP),
                "entities": dict(entities or {}),
            }
        },
    }


@dataclass
class RunnerResult:
    out_dir: Path
    export_path: Path
    manifest_path: Path
    mapping_path: Path
    report_path: Path
    index_path: Path
    report: Dict[str, Any]


def collect_profile(
    profile: SourceProfile,
    out_dir: Path,
    *,
    fetcher: Optional[HttpFetcher] = None,
    capture_index: Optional[Path] = None,
    synthetic: bool = False,
    now: Optional[str] = None,
    fixture_entities: Optional[Dict[str, Dict[str, str]]] = None,
) -> RunnerResult:
    """Collect/extract one profile and write a normalized acquisition export.

    Exactly one input mode is required: ``fetcher`` (live HTTP) or
    ``capture_index`` (offline replay of verified raw captures).
    """

    if (fetcher is None) == (capture_index is None):
        raise RunnerError(
            "input_mode_required",
            "pass exactly one of fetcher= (live) or capture_index= (offline)",
        )

    # Reuse gate: the declared policy is decided once, here, before this
    # function can touch the network, re-read an offline index, create the
    # output directory or extract anything. ``synthetic=True`` marks test data;
    # it is not a permission, so it must not bypass this refusal. A source whose
    # reuse is not explicitly permitted therefore yields no capture and no POI
    # at all, which is what the downstream quarantine rules assume.
    gate = gate_for_profile(profile)
    if gate is not None:
        raise RunnerError(gate.reason, gate.detail())

    if len(profile.start_urls) > profile.max_content_urls:
        raise RunnerError("content_budget_exceeded", profile.name)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"
    policy_dir = out_dir / "policy"

    policy_entries: List[CaptureIndexEntry] = []
    robots: Dict[str, RobotsDecision] = {}
    failures: List[Dict[str, str]] = []
    if fetcher is not None:
        policy_entries, robots = _fetch_policy_and_robots(profile, fetcher, policy_dir)
        captures, failures = _fetch_content(profile, fetcher, raw_dir)
        content_entries = _index_entries(captures, kind="content")
    else:
        captures, all_entries, policy_bodies = load_capture_index(Path(capture_index))
        content_entries = [entry for entry in all_entries if entry.kind == "content"]
        policy_entries = [entry for entry in all_entries if entry.kind == "policy"]
        for policy_capture in policy_bodies:
            if policy_capture.url.endswith("/robots.txt"):
                host = urlsplit(policy_capture.url).hostname or ""
                robots[host] = evaluate_robots(
                    policy_capture, urlsplit(profile.start_urls[0]).path
                )
        for host, decision in robots.items():
            if not decision.allowed:
                raise RunnerError("robots_disallowed", f"{host}: {decision.matched_rule}")
        # An offline replay must cover the declared URLs; a missing page is a
        # failure, never a silently smaller sample.
        missing = [url for url in profile.start_urls if url not in captures]
        failures.extend(
            {"url": url, "reason": "capture_missing", "detail": "offline index"}
            for url in missing
        )

    extraction_records: List[Any] = []
    extraction_errors: List[Dict[str, str]] = []
    used_captures: List[Capture] = []
    for url in profile.start_urls:
        found = captures.get(url)
        if found is None:
            continue
        capture, file = found
        if sha256_bytes(capture.body) != capture.sha256:
            raise RunnerError("capture_hash_mismatch", url)
        result = _extract(profile, capture, file)
        extraction_records.extend(result.records)
        extraction_errors.extend(result.errors)
        used_captures.append(capture)

    if not used_captures:
        raise RunnerError(
            "no_content_captures",
            "; ".join(f"{item['url']}={item['reason']}" for item in failures),
        )

    combined = ExtractionResult(records=extraction_records, errors=extraction_errors)
    records, counts = _normalize_records(profile, combined)

    generated_at = now or (used_captures[-1].fetched_at or _utc_now())
    policy_payload = {
        "license": profile.license,
        "reuse_status": profile.reuse_status,
        "reuse_permitted": policy_allows_reuse(profile),
        "notes": profile.notes,
        "evidence": _policy_evidence(profile),
        "robots": {host: decision.as_dict() for host, decision in robots.items()},
    }
    source_attribution = _attribution(
        profile, profile.start_urls[0] if profile.start_urls else ""
    )
    if source_attribution is not None:
        policy_payload["attribution"] = source_attribution
    source_block = {
        "source_id": profile.source_id,
        "profile": profile.name,
        "source_type": "web_poi",
        "license": profile.license,
        "reuse_status": profile.reuse_status,
        "policy_evidence": policy_payload["evidence"],
    }
    if source_attribution is not None:
        source_block["attribution"] = source_attribution
        source_block["attribution_required"] = True
    export = {
        "schema_version": SCHEMA_VERSION,
        "synthetic": bool(synthetic),
        "source": source_block,
        "captures": [
            {"url": capture.url, **capture.metadata()} for capture in used_captures
        ],
        "records": records,
    }
    export_path = out_dir / "export.json"
    atomic_write_json(export_path, export)

    manifest_source = {
        "source_id": profile.source_id,
        "source_type": "web_poi",
        "source_url": profile.start_urls[0],
        "license": profile.license,
        "retrieved_at": generated_at,
        "export_path": export_path.name,
        "synthetic": bool(synthetic),
    }
    if source_attribution is not None:
        # Kept alongside the licence so the attribution obligation is visible to
        # whoever consumes the manifest, not only to readers of the export.
        manifest_source["attribution"] = source_attribution
    manifest = {
        "manifest_version": 1,
        "dataset": profile.dataset,
        "synthetic": bool(synthetic),
        "sources": [manifest_source],
    }
    manifest_path = out_dir / "acquisition_manifest.json"
    atomic_write_json(manifest_path, manifest)

    mapping = build_mapping(
        profile, synthetic=synthetic, entities=fixture_entities
    )
    mapping_path = out_dir / "mapping.json"
    atomic_write_json(mapping_path, mapping)

    index_path = out_dir / "capture_index.json"
    index_entries = policy_entries + content_entries
    atomic_write_json(
        index_path,
        {
            "schema_version": SCHEMA_VERSION,
            "profile": profile.name,
            "entries": [entry.as_dict() for entry in index_entries],
        },
    )

    counts.update(
        {
            "content_pages": len(used_captures),
            "policy_fetches": len(policy_entries),
            "fetch_failures": len(failures),
            "exported_records": len(records),
            "imported": 0,
        }
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "profile": profile.name,
        "source_id": profile.source_id,
        "synthetic": bool(synthetic),
        "generated_at": generated_at,
        "mode": "live_http" if fetcher is not None else "offline_replay",
        "policy": policy_payload,
        "counts": counts,
        "captures": [
            {"url": capture.url, **capture.metadata()} for capture in used_captures
        ],
        "policy_captures": [entry.as_dict() for entry in policy_entries],
        "failures": failures,
        "extraction_errors": extraction_errors[:_MAX_REPORT_EVIDENCE],
        "records_preview": [
            {
                "record_id": record["record_id"],
                "name": record["name"],
                "issues": record["issues"],
                "minimum_valid": record["minimum_valid"],
                "locator": record["locator"],
            }
            for record in records[:_MAX_REPORT_EVIDENCE]
        ],
        "limitations": [
            "P0/P1 output only: no graph write, no ingestion POST, imported=0.",
            "Coordinates are absent unless explicitly present in a reviewed record.",
            "License/admin/category review is never inferred by this pipeline.",
        ]
        + (
            [
                "Declared licence requires attribution: the notice is carried by "
                "the source block and by every record, and share_alike applies to "
                "any downstream reuse of this text.",
            ]
            if source_attribution is not None
            else []
        ),
    }
    report_path = out_dir / "report.json"
    atomic_write_json(report_path, report)

    return RunnerResult(
        out_dir=out_dir,
        export_path=export_path,
        manifest_path=manifest_path,
        mapping_path=mapping_path,
        report_path=report_path,
        index_path=index_path,
        report=report,
    )
