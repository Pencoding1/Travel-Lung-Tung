"""Controlled multi-city Wikivoyage ingestion & entity-review orchestrator (KT-10).

Supports two explicit modes:
* ``--mode dry-run`` (default): offline deterministic verification using an
  in-memory fake transport (zero network calls, zero mutation of frozen ``data/``).
  Produces the full ``social_ingest`` + ``acquisition`` bundle plus a structured
  ``entity_review_template.json`` for operator curation.
* ``--mode fetch``: operator-gated live HTTP crawl for the selected CC-BY-SA-4.0
  Wikivoyage profile(s), respecting ``robots.txt`` and rate limits, followed by
  the acquisition pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from crawler_service.app.acquisition.pipeline import run_pipeline

from crawler_service.app.social_ingest import cli as social_cli
from crawler_service.app.social_ingest.fetch import (
    FetchPolicy,
    HttpFetcher,
    TransportResponse,
)
from crawler_service.app.social_ingest.profiles import (
    REUSE_PERMITTED,
    SourceProfile,
    gate_for_profile,
    get_profile,
    list_profiles,
)
from crawler_service.app.social_ingest.runner import collect_profile

MULTI_CITY_PROFILES: Sequence[str] = (
    "wikivoyage_en_hcmc",
    "wikivoyage_en_danang",
    "wikivoyage_en_hoian",
    "wikivoyage_en_hue",
    "wikivoyage_en_dalat",
    "wikivoyage_en_hanoi",
)

_ROBOTS_TXT = (
    "User-agent: *\n"
    "Disallow: /w/\n"
    "Disallow: /api/\n"
    "Disallow: /Special:\n"
)


def _synthetic_city_html(profile: SourceProfile) -> str:
    slug = profile.start_urls[0].rsplit("/", 1)[-1].replace("_", " ")
    anchor = slug.lower().replace(" ", "-")
    return (
        f"<html><body>"
        f"<h2><span class=\"mw-headline\" id=\"See\">See</span></h2>"
        f"<div class=\"vcard\" id=\"{anchor}-heritage-museum\">"
        f"  <span class=\"fn org listing-name\">{slug} Heritage Museum (dry-run)</span>"
        f"  <span class=\"adr\"><span class=\"street-address listing-address\">"
        f"1 Central Avenue, {slug}</span></span>"
        f"  <span class=\"geo listing-coordinates\">"
        f"    <abbr class=\"latitude\">16.06778</abbr>"
        f"    <abbr class=\"longitude\">108.22083</abbr>"
        f"  </span>"
        f"  <span class=\"note listing-content\">Historic cultural museum in {slug}.</span>"
        f"</div>"
        f"</body></html>"
    )


def _offline_fetcher_for(profile: SourceProfile) -> HttpFetcher:
    html_bytes = _synthetic_city_html(profile).encode("utf-8")
    robots_url = f"https://{profile.host}/robots.txt"
    responses: Dict[str, TransportResponse] = {
        robots_url: TransportResponse(
            200, {"content-type": "text/plain; charset=utf-8"}, _ROBOTS_TXT.encode("utf-8")
        ),
    }
    for url in profile.start_urls:
        responses[url] = TransportResponse(
            200, {"content-type": "text/html; charset=utf-8"}, html_bytes
        )

    def _transport(url: str, timeout: float, headers: Dict[str, str]) -> TransportResponse:
        if url not in responses:
            return TransportResponse(404, {"content-type": "text/plain"}, b"not found")
        return responses[url]

    return HttpFetcher(
        FetchPolicy(
            allow_hosts=profile.allow_hosts,
            timeout_seconds=1.0,
            max_bytes=200_000,
            retries=0,
            min_interval_seconds=0.0,
        ),
        transport=_transport,
        resolver=lambda host, port: ["93.184.216.34"],
        profile=profile,
        clock=lambda: 0.0,
        sleep=lambda seconds: None,
        wall_clock=lambda: "2026-11-07T00:00:00Z",
    )


def build_entity_review_template(export_path: Path, output_path: Path) -> Dict[str, object]:
    """Create an operator entity-review template from a social_ingest export."""
    export_doc = json.loads(export_path.read_text(encoding="utf-8"))
    source = export_doc.get("source") or {}
    entries: List[Dict[str, object]] = []
    for record in export_doc.get("records") or []:
        entries.append(
            {
                "record_id": record.get("record_id"),
                "name": record.get("name"),
                "address_raw": record.get("address_raw"),
                "coordinates": record.get("coordinates"),
                "proposed_category": None,
                "review_decision": "PENDING_OPERATOR_REVIEW",
                "license": source.get("license"),
                "attribution_required": source.get("attribution_required", False),
                "source_url": record.get("page_url"),
            }
        )
    template = {
        "schema": "tvlt.entity_review_template.v1",
        "source_id": source.get("source_id"),
        "profile": source.get("profile"),
        "license": source.get("license"),
        "synthetic": bool(export_doc.get("synthetic", False)),
        "total_records": len(entries),
        "records": entries,
    }
    output_path.write_text(
        json.dumps(template, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return template


def run_city_workflow(
    profile_name: str,
    out_root: Path,
    *,
    mode: str = "dry-run",
) -> Dict[str, object]:
    profile = get_profile(profile_name)
    gate = gate_for_profile(profile)
    if gate is not None or profile.reuse_status != REUSE_PERMITTED:
        raise ValueError(f"Profile {profile_name!r} is not permitted for reuse")

    city_dir = out_root / profile_name
    ingest_dir = city_dir / "social_ingest"
    acq_dir = city_dir / "acquisition"

    if mode == "dry-run":
        fetcher = _offline_fetcher_for(profile)
        ingest_result = collect_profile(
            profile, ingest_dir, fetcher=fetcher, synthetic=True
        )
    elif mode == "fetch":
        fetcher = social_cli._fetcher_for(profile)
        ingest_result = collect_profile(
            profile, ingest_dir, fetcher=fetcher, synthetic=False
        )
    else:
        raise ValueError(f"Unknown mode: {mode!r}")

    acq_result = run_pipeline(
        ingest_result.manifest_path,
        ingest_result.mapping_path,
        acq_dir,
        dry_run=True,
    )

    review_path = city_dir / "entity_review_template.json"
    review_template = build_entity_review_template(
        ingest_result.export_path, review_path
    )

    return {
        "profile": profile.name,
        "source_id": profile.source_id,
        "license": profile.license,
        "mode": mode,
        "synthetic": (mode == "dry-run"),
        "extracted_records": ingest_result.report["counts"]["extracted_records"],
        "acquisition_totals": acq_result.summary["totals"],
        "entity_review_template": str(review_path),
        "review_records": review_template["total_records"],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Multi-city Wikivoyage ingestion & review workflow (KT-10)."
    )
    parser.add_argument(
        "--profiles",
        default=",".join(MULTI_CITY_PROFILES),
        help="Comma-separated profile names (default: all 6 Wikivoyage city profiles).",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output directory for ingestion, acquisition, and review artifacts.",
    )
    parser.add_argument(
        "--mode",
        choices=("dry-run", "fetch"),
        default="dry-run",
        help="'dry-run' uses offline synthetic transport; 'fetch' performs live HTTP.",
    )
    args = parser.parse_args(argv)

    out_root = Path(args.out).resolve()
    requested = [p.strip() for p in args.profiles.split(",") if p.strip()]
    summaries = []
    for name in requested:
        summaries.append(run_city_workflow(name, out_root, mode=args.mode))

    print(
        json.dumps(
            {
                "status": "completed",
                "mode": args.mode,
                "cities_processed": len(summaries),
                "cities": summaries,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
