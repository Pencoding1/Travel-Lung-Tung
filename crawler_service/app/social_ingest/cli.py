"""CLI for the OC-050 web POI collection and ingestion-planning steps.

Examples (repository root)::

    python -m crawler_service.app.social_ingest.cli list
    python -m crawler_service.app.social_ingest.cli crawl \
        --profile vietnam_travel_hcmc7 \
        --out data/social_expansion_20261018/real --fetch
    python -m crawler_service.app.social_ingest.cli crawl \
        --profile vietnam_travel_hcmc7 \
        --out data/social_expansion_20261018/real \
        --capture-index data/social_expansion_20261018/real/capture_index.json
    python -m crawler_service.app.social_ingest.cli plan \
        --accepted <acquisition-out>/accepted.jsonl \
        --candidates <acquisition-out>/candidates.jsonl \
        --out data/social_expansion_20261018/real/ingestion --dataset social_web_oc050

Live collection is opt-in (``--fetch``); the default collection mode requires
an existing capture index. The ingestion plan command is always dry-run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .fetch import FetchPolicy, HttpFetcher
from .ingest import IngestError, build_ingest_plan
from .profiles import get_profile, list_profiles
from .runner import RunnerError, collect_profile


def _fetcher_for(profile) -> HttpFetcher:
    policy = FetchPolicy(
        allow_hosts=tuple(profile.allow_hosts),
        timeout_seconds=15.0,
        max_bytes=2_000_000,
        max_redirects=3,
        retries=1,
        min_interval_seconds=1.5,
    )
    return HttpFetcher(policy)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crawler_service.app.social_ingest.cli",
        description="Bounded HTTP-only web POI collection (dry-run; no graph writes).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List declared source profiles and reuse status.")

    crawl = sub.add_parser("crawl", help="Fetch or replay one profile and build a web_poi export.")
    crawl.add_argument("--profile", required=True)
    crawl.add_argument("--out", required=True, type=Path)
    crawl.add_argument(
        "--fetch", action="store_true", help="Opt in to bounded live HTTP collection."
    )
    crawl.add_argument(
        "--capture-index",
        type=Path,
        default=None,
        help="Offline replay: verified capture index written by a previous --fetch run.",
    )

    plan = sub.add_parser("plan", help="Build a dry-run ingestion payload/evidence plan.")
    plan.add_argument("--accepted", required=True, type=Path)
    plan.add_argument("--candidates", required=True, type=Path)
    plan.add_argument("--out", required=True, type=Path)
    plan.add_argument("--dataset", default="social_web_oc050")
    plan.add_argument("--synthetic", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list":
        payload = {
            name: {
                "source_id": profile.source_id,
                "host": profile.host,
                "start_urls": list(profile.start_urls),
                "extractor": profile.extractor,
                "license": profile.license,
                "reuse_status": profile.reuse_status,
                "attribution_required": profile.attribution_required,
                "share_alike": profile.share_alike,
            }
            for name, profile in list_profiles().items()
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return 0

    if args.command == "crawl":
        if args.fetch == bool(args.capture_index):
            sys.stderr.write(
                "choose exactly one input mode: --fetch (live) or --capture-index (offline)\n"
            )
            return 2
        try:
            profile = get_profile(args.profile)
            result = collect_profile(
                profile,
                args.out,
                fetcher=_fetcher_for(profile) if args.fetch else None,
                capture_index=args.capture_index,
            )
        except (RunnerError, KeyError) as exc:
            sys.stderr.write(f"crawl failed: {exc}\n")
            return 2
        sys.stdout.write(
            json.dumps(
                {
                    "status": "ok",
                    "profile": result.report["profile"],
                    "mode": result.report["mode"],
                    "counts": result.report["counts"],
                    "export": str(result.export_path),
                    "manifest": str(result.manifest_path),
                    "mapping": str(result.mapping_path),
                    "report": str(result.report_path),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        return 0

    if args.command == "plan":
        try:
            plan = build_ingest_plan(
                args.accepted,
                args.candidates,
                args.out,
                dataset=args.dataset,
                synthetic=args.synthetic,
                dry_run=True,
            )
        except (IngestError, OSError) as exc:
            sys.stderr.write(f"plan failed: {exc}\n")
            return 2
        sys.stdout.write(json.dumps(plan, ensure_ascii=False, sort_keys=True) + "\n")
        return 0

    parser.error("unknown command")  # pragma: no cover
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
