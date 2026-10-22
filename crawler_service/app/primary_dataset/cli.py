"""Bounded offline CLI for primary dataset preparation.

Example (from the repository root)::

    .venv-validation/Scripts/python.exe -m crawler_service.app.primary_dataset.cli \
        --input data/primary_20261016/hcm_pois_final.geojson \
        --out data/primary_20261016/prepared

The CLI only ever prepares local artifacts: it never contacts the network and
never writes to the graph.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from crawler_service.app.acquisition.resolution import ConfigError

from . import DEFAULT_INPUT, DEFAULT_OUT_DIR, DEFAULT_PROVIDED_AT
from .prepare import prepare_primary_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crawler_service.app.primary_dataset.cli",
        description="Prepare the primary GeoJSON into schema-validated POI candidates.",
    )
    parser.add_argument("--input", type=Path, default=Path(DEFAULT_INPUT))
    parser.add_argument("--out", type=Path, default=Path(DEFAULT_OUT_DIR))
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Persistent local identity registry (default: <out>/identity_registry.json).",
    )
    parser.add_argument(
        "--provided-at",
        default=DEFAULT_PROVIDED_AT,
        help="Declared provided-at date (not a retrieval time).",
    )
    parser.add_argument(
        "--accept-input-revision",
        action="store_true",
        help="Explicitly accept changed identity fields / a new input revision.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = prepare_primary_dataset(
            args.input,
            args.out,
            args.registry,
            provided_at=args.provided_at,
            accept_input_revision=args.accept_input_revision,
        )
    except ConfigError as exc:
        sys.stderr.write(f"configuration error: {exc}\n")
        return 2
    sys.stdout.write(
        json.dumps(
            {
                "status": "ok",
                "summary": str(result.outputs["summary"]),
                "counts": result.summary["counts"],
                "sumcheck": result.summary["sumcheck"],
                "assigned_in_this_run": result.assigned_in_this_run,
                "registry_changed": result.registry_changed,
                "revision_accepted": result.revision_accepted,
                "registry": str(result.registry_path),
            },
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
