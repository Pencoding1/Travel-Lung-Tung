"""Dry-run CLI for the acquisition pipeline.

Example (from the repository root)::

    .venv-validation/Scripts/python.exe -m crawler_service.app.acquisition.cli \
        --manifest data/acquisition/examples/manifest.example.json \
        --mapping data/acquisition/examples/mapping.example.json \
        --out data/acquisition/examples/out

The CLI only ever performs a dry run: it never contacts the network and never
writes to the graph. Extra positional arguments are rejected.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .pipeline import run_pipeline
from .resolution import ConfigError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crawler_service.app.acquisition.cli",
        description="Deterministic dry-run POI acquisition (no live ingestion).",
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--now",
        default=None,
        help="Optional UTC ISO-8601 timestamp for reproducible decisions.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Accepted for explicitness; the pipeline is always a dry run.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_pipeline(
            args.manifest,
            args.mapping,
            args.out,
            now=args.now,
            dry_run=True,
        )
    except ConfigError as exc:
        sys.stderr.write(f"configuration error: {exc}\n")
        return 2
    sys.stdout.write(
        json.dumps(
            {
                "status": "ok",
                "summary": str(result.summary_path),
                "totals": result.summary["totals"],
                "real_expansion_totals": result.summary["real_expansion_totals"],
                "synthetic": result.summary["synthetic"],
                "scope": result.summary["scope"],
            },
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
