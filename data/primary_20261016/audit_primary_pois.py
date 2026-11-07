#!/usr/bin/env python3
"""Reproducible, stdlib-only audit of the supplied primary POI GeoJSON (OC-032).

Reads the immutable primary dataset once, verifies raw integrity, and emits a
deterministic JSON report describing schema, coverage, coordinate consistency,
quality, vocabularies and duplicate structure.

Design constraints (see OC-032 brief):
  * No third-party imports, no network, no model calls.
  * The raw dataset is opened read-only and never mutated.
  * All counts are computed in input order; only vocabulary listings are sorted
    so the report is byte-stable across runs.
  * Nothing is accepted/ingested; the script only characterises the file and
    proposes a derived candidate identity for later review.

Usage:
    python audit_primary_pois.py [--geojson PATH] [--json-out PATH]

Exit code is 0 when the file parses; 2 on I/O or parse failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

DEFAULT_GEOJSON = Path(__file__).with_name("hcm_pois_final.geojson")
HCMC_BBOX = (10.3, 11.2, 106.3, 107.1)  # informational only, not a validity gate
SOURCE_NAMESPACE = "hcm_primary_geojson"  # proposed derived namespace

# Closed structural criteria: a record is structurally valid only when all hold.
REQUIRED_STRING_FIELDS = ("name", "processed_name", "poi_category", "addr_city", "addr_district")
OPTIONAL_STRING_FIELDS = ("opening_ho", "addr_full", "addr_house", "addr_stree", "addr_ward")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def finite_number(v) -> bool:
    return is_number(v) and math.isfinite(v)


def nonblank_str(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def normalize_name(text) -> str:
    """Deterministic comparison key: accents folded, lowercase, alnum only.

    This is a *comparison* key for duplicate review, never an identity claim.
    """
    if not isinstance(text, str):
        return ""
    folded = unicodedata.normalize("NFKD", text)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_only.lower())


def round_coord(value, places: int = 6):
    if not finite_number(value):
        return None
    return round(float(value), places)


def derived_candidate_key(feature: dict) -> str:
    """Namespaced hash compatible with crawler_service stable_source_id().

    IMPORTANT: the supplied file carries NO genuine source entity id, so this is
    a *derived candidate identity*, explicitly not a cross-export stable source
    identifier. It is computed only from normalized name + rounded coordinates
    so it never depends on row index or on the raw file hash.
    """
    props = feature.get("properties") or {}
    name_key = normalize_name(props.get("name"))
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") if isinstance(geom, dict) else None
    coord_key = ""
    if isinstance(coords, list) and len(coords) == 2:
        coord_key = f"{round_coord(coords[0])},{round_coord(coords[1])}"
    material = f"{SOURCE_NAMESPACE}\x1f{name_key}\x1f{coord_key}".encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    return f"{SOURCE_NAMESPACE}:derived:{digest[:32]}"


def audit(geojson_path: Path) -> dict:
    raw_bytes = geojson_path.read_bytes()
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    doc = json.loads(raw_bytes.decode("utf-8"))

    features = doc.get("features")
    if not isinstance(features, list):
        raise ValueError("top-level 'features' is missing or not a list")

    report: "OrderedDict" = OrderedDict()
    report["input"] = {
        "path": str(geojson_path.as_posix()),
        "bytes": len(raw_bytes),
        "sha256": raw_sha256,
        "declared_expected_sha256": "713b07a62cf89bd2cad9093abaad2a4c5f01e23853321764b3d66bf9f7eee43c",
        "declared_expected_bytes": 2712731,
        "declared_expected_features": 6368,
    }
    report["input"]["sha256_matches_brief"] = (
        raw_sha256 == report["input"]["declared_expected_sha256"]
    )
    report["input"]["bytes_matches_brief"] = len(raw_bytes) == 2712731

    top = OrderedDict()
    top["type"] = doc.get("type")
    top["name"] = doc.get("name")
    top["crs"] = doc.get("crs")
    top["top_level_keys"] = sorted(doc.keys())
    report["top_level"] = top

    # ---- per-feature scan -------------------------------------------------
    geom_type_counter = Counter()
    geometry_missing = 0
    geometry_not_point = 0
    geometry_bad_shape = 0
    coord_nonfinite = 0
    coord_out_of_range = 0
    coord_consistency_mismatch = 0
    coord_consistency_max_absdiff = 0.0
    prop_latlon_missing_or_nonfinite = 0
    prop_latlon_out_of_range = 0
    outside_hcm_bbox = 0
    feature_type_counter = Counter()
    property_key_union = Counter()
    property_keys_per_feature = Counter()
    field_null = Counter()
    field_blank = Counter()
    field_type_violation = Counter()
    field_present = Counter()
    poi_category_counter = Counter()
    addr_city_counter = Counter()
    addr_district_counter = Counter()
    addr_ward_counter = Counter()
    cluster_counter = Counter()
    opening_hours_present = 0
    opening_hours_values = Counter()
    addr_full_present = 0
    addr_house_present = 0
    addr_stree_present = 0
    addr_ward_present = 0
    processed_name_present = 0
    id_like_keys = Counter()

    required_string_fields = set(REQUIRED_STRING_FIELDS)
    optional_string_fields = set(OPTIONAL_STRING_FIELDS)

    exact_feature_hash_counter = Counter()
    name_coord_counter = Counter()
    normalized_name_counter = Counter()
    exact_feature_members = defaultdict(list)
    name_coord_members = defaultdict(list)
    processed_name_missing_examples = []
    replacement_char_features = 0
    control_char_features = 0
    non_ascii_name_features = 0
    non_ascii_stree_features = 0
    non_ascii_ward_features = 0

    per_feature_structurally_valid = 0
    per_feature_review_reasons = Counter()

    derived_keys = []
    derived_dupe = Counter()

    for idx, feat in enumerate(features):
        if not isinstance(feat, dict):
            feature_type_counter["not_object"] += 1
            per_feature_review_reasons["feature_not_object"] += 1
            continue
        feature_type_counter[str(feat.get("type"))] += 1

        props = feat.get("properties")
        if not isinstance(props, dict):
            props = {}
            per_feature_review_reasons["properties_missing"] += 1
        for key in props:
            property_key_union[key] += 1
            if "id" in key.lower():
                id_like_keys[key] += 1
        property_keys_per_feature[len(props)] += 1

        feature_local_reasons = []

        # --- required string fields ---
        for fname in REQUIRED_STRING_FIELDS:
            if fname not in props:
                field_null[fname] += 1
                feature_local_reasons.append(f"missing_required:{fname}")
                continue
            value = props.get(fname)
            if value is None:
                field_null[fname] += 1
                feature_local_reasons.append(f"missing_required:{fname}")
            elif not nonblank_str(value):
                if isinstance(value, str):
                    field_blank[fname] += 1
                else:
                    field_type_violation[fname] += 1
                feature_local_reasons.append(f"invalid_required:{fname}")
            else:
                field_present[fname] += 1

        # --- optional string fields ---
        for fname in OPTIONAL_STRING_FIELDS:
            if fname not in props or props.get(fname) is None:
                field_null[fname] += 1
                continue
            value = props.get(fname)
            if not nonblank_str(value):
                if isinstance(value, str):
                    field_blank[fname] += 1
                else:
                    field_type_violation[fname] += 1
            else:
                field_present[fname] += 1

        if nonblank_str(props.get("opening_ho")):
            opening_hours_present += 1
            opening_hours_values[str(props.get("opening_ho"))] += 1
        if nonblank_str(props.get("addr_full")):
            addr_full_present += 1
        if nonblank_str(props.get("addr_house")):
            addr_house_present += 1
        if nonblank_str(props.get("addr_stree")):
            addr_stree_present += 1
        if nonblank_str(props.get("addr_ward")):
            addr_ward_present += 1
        if nonblank_str(props.get("processed_name")):
            processed_name_present += 1

        cat = props.get("poi_category")
        if nonblank_str(cat):
            poi_category_counter[str(cat)] += 1
        city = props.get("addr_city")
        if nonblank_str(city):
            addr_city_counter[str(city)] += 1
        district = props.get("addr_district")
        if nonblank_str(district):
            addr_district_counter[str(district)] += 1
        ward = props.get("addr_ward")
        if nonblank_str(ward):
            addr_ward_counter[str(ward)] += 1

        cluster = props.get("cluster")
        if isinstance(cluster, (int, float)) and not isinstance(cluster, bool):
            cluster_counter[str(cluster)] += 1
        else:
            cluster_counter[f"<{type(cluster).__name__}>"] += 1

        # --- property lat/lon ---
        lat = props.get("lat")
        lon = props.get("lon")
        lat_ok = finite_number(lat)
        lon_ok = finite_number(lon)
        if not (lat_ok and lon_ok):
            prop_latlon_missing_or_nonfinite += 1
            feature_local_reasons.append("property_latlon_missing_or_nonfinite")
        else:
            if not (-90.0 <= float(lat) <= 90.0) or not (-180.0 <= float(lon) <= 180.0):
                prop_latlon_out_of_range += 1
                feature_local_reasons.append("property_latlon_out_of_range")

        # --- geometry ---
        geom = feat.get("geometry")
        if geom is None:
            geometry_missing += 1
            feature_local_reasons.append("geometry_missing")
        elif not isinstance(geom, dict):
            geometry_bad_shape += 1
            feature_local_reasons.append("geometry_not_object")
        else:
            gtype = geom.get("type")
            geom_type_counter[str(gtype)] += 1
            if gtype != "Point":
                geometry_not_point += 1
                feature_local_reasons.append("geometry_not_point")
            coords = geom.get("coordinates")
            if not (isinstance(coords, list) and len(coords) == 2):
                geometry_bad_shape += 1
                feature_local_reasons.append("geometry_coordinate_shape")
            else:
                cx, cy = coords[0], coords[1]
                if not (finite_number(cx) and finite_number(cy)):
                    coord_nonfinite += 1
                    feature_local_reasons.append("geometry_coord_nonfinite")
                else:
                    if not (-180.0 <= float(cx) <= 180.0) or not (-90.0 <= float(cy) <= 90.0):
                        coord_out_of_range += 1
                        feature_local_reasons.append("geometry_coord_out_of_range")
                    # informational geographic extent check (not a validity gate)
                    if not (HCMC_BBOX[0] <= float(cy) <= HCMC_BBOX[1]) or not (
                        HCMC_BBOX[2] <= float(cx) <= HCMC_BBOX[3]
                    ):
                        per_feature_review_reasons["outside_hcm_bbox"] += 1
                    # lon/lat vs property consistency (geometry is [lon, lat])
                    if lat_ok and lon_ok:
                        dx = abs(float(cx) - float(lon))
                        dy = abs(float(cy) - float(lat))
                        diff = max(dx, dy)
                        coord_consistency_max_absdiff = max(coord_consistency_max_absdiff, diff)
                        if diff != 0.0:
                            coord_consistency_mismatch += 1
                            feature_local_reasons.append("geometry_property_mismatch")

        # --- encoding / text integrity ---
        for fname in ("name", "addr_stree", "addr_ward"):
            val = props.get(fname)
            if isinstance(val, str):
                has_non_ascii = any(ord(ch) > 127 for ch in val)
                if has_non_ascii and fname == "name":
                    non_ascii_name_features += 1
                if has_non_ascii and fname == "addr_stree":
                    non_ascii_stree_features += 1
                if has_non_ascii and fname == "addr_ward":
                    non_ascii_ward_features += 1
        all_str_values = [v for v in props.values() if isinstance(v, str)]
        if any("\ufffd" in v for v in all_str_values):
            replacement_char_features += 1
        if any(any(ord(ch) < 32 and ch not in "\t\n\r" for ch in v) for v in all_str_values):
            control_char_features += 1

        # --- duplicate keys ---
        exact_key = hashlib.sha256(
            json.dumps(feat, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        exact_feature_hash_counter[exact_key] += 1
        name_key = normalize_name(props.get("name"))
        coord_key = ""
        if isinstance(geom, dict) and isinstance(geom.get("coordinates"), list) and len(geom["coordinates"]) == 2:
            coord_key = f"{round_coord(geom['coordinates'][0])},{round_coord(geom['coordinates'][1])}"
        name_coord_key = f"{name_key}|{coord_key}"
        name_coord_counter[name_coord_key] += 1
        normalized_name_counter[name_key] += 1

        member = OrderedDict((
            ("index", idx),
            ("name", props.get("name")),
            ("normalized_name", name_key),
            ("coordinates", coord_key),
            ("cluster", props.get("cluster")),
        ))
        exact_feature_members[exact_key].append(member)
        name_coord_members[name_coord_key].append(member)

        if "missing_required:processed_name" in feature_local_reasons:
            processed_name_missing_examples.append(member)

        dkey = derived_candidate_key(feat)
        derived_keys.append(dkey)
        derived_dupe[dkey] += 1

        if feature_local_reasons:
            for reason in feature_local_reasons:
                per_feature_review_reasons[reason] += 1
        else:
            per_feature_structurally_valid += 1

    # ---- duplicate summaries ---------------------------------------------
    def dup_groups(counter: Counter) -> dict:
        groups = {k: v for k, v in counter.items() if v > 1}
        extra_records = sum(v - 1 for v in groups.values())
        return {
            "distinct_keys": len(counter),
            "duplicate_group_count": len(groups),
            "extra_records_beyond_first": extra_records,
            "max_group_size": max(counter.values()) if counter else 0,
        }

    report["schema"] = {
        "feature_type_count": dict(sorted(feature_type_counter.items())),
        "geometry_type_count": dict(sorted(geom_type_counter.items())),
        "property_key_union": dict(sorted(property_key_union.items())),
        "property_keys_per_feature": dict(sorted(property_keys_per_feature.items())),
        "id_like_property_keys": dict(sorted(id_like_keys.items())),
        "field_present": {k: field_present[k] for k in sorted(field_present)},
        "field_null_or_absent": {k: v for k, v in sorted(field_null.items())},
        "field_blank": {k: v for k, v in sorted(field_blank.items())},
        "field_type_violation": {k: v for k, v in sorted(field_type_violation.items())},
    }

    report["quality"] = {
        "geometry_missing": geometry_missing,
        "geometry_not_point": geometry_not_point,
        "geometry_bad_coordinate_shape": geometry_bad_shape,
        "geometry_coord_nonfinite": coord_nonfinite,
        "geometry_coord_out_of_range": coord_out_of_range,
        "property_latlon_missing_or_nonfinite": prop_latlon_missing_or_nonfinite,
        "property_latlon_out_of_range": prop_latlon_out_of_range,
        "geometry_property_mismatch_count": coord_consistency_mismatch,
        "geometry_property_max_abs_diff": coord_consistency_max_absdiff,
        "outside_hcm_bbox_informational": per_feature_review_reasons["outside_hcm_bbox"],
        "structurally_valid": per_feature_structurally_valid,
        "review_needed": len(features) - per_feature_structurally_valid,
        "review_reason_counts": dict(sorted(per_feature_review_reasons.items())),
        "criteria": {
            "structurally_valid_requires": [
                "geometry is a Point with 2 finite coordinates in global range",
                "property lat/lon present, finite, in global range, exactly equal to geometry",
                "nonblank required strings: " + ", ".join(REQUIRED_STRING_FIELDS),
            ],
            "note": "optional-field absence (hours/prices/ward/etc.) is a completeness gap, not a structural failure",
        },
    }

    report["completeness"] = {
        "opening_hours_present": opening_hours_present,
        "opening_hours_absent": len(features) - opening_hours_present,
        "opening_hours_distinct_values": dict(sorted(opening_hours_values.items())),
        "addr_full_present": addr_full_present,
        "addr_house_present": addr_house_present,
        "addr_stree_present": addr_stree_present,
        "addr_ward_present": addr_ward_present,
        "processed_name_present": processed_name_present,
        "price_fields_present": [],
        "route_evidence_fields_present": [],
        "note": "no price/route columns exist in the supplied schema",
    }

    report["vocabularies"] = {
        "poi_category_distinct": len(poi_category_counter),
        "poi_category_counts": dict(sorted(poi_category_counter.items())),
        "addr_city_distinct": len(addr_city_counter),
        "addr_city_counts": dict(sorted(addr_city_counter.items())),
        "addr_district_distinct": len(addr_district_counter),
        "addr_district_counts": dict(sorted(addr_district_counter.items())),
        "addr_ward_distinct": len(addr_ward_counter),
        "addr_ward_counts": dict(sorted(addr_ward_counter.items())),
        "cluster_counts": dict(sorted(cluster_counter.items())),
    }

    def group_examples(members_map: dict, counter: Counter, limit: int = 10) -> list:
        rows = []
        for key, count in counter.most_common():
            if count <= 1 or len(rows) >= limit:
                continue
            rows.append({"count": count, "members": members_map[key]})
        return rows

    report["duplicates"] = {
        "exact_feature": dup_groups(exact_feature_hash_counter),
        "normalized_name_plus_coordinate": dup_groups(name_coord_counter),
        "normalized_name_only": dup_groups(normalized_name_counter),
        "derived_candidate_key": dup_groups(derived_dupe),
        "distinct_derived_candidate_ids": len(set(derived_keys)),
        "exact_feature_groups": group_examples(exact_feature_members, exact_feature_hash_counter),
        "normalized_name_plus_coordinate_groups": group_examples(
            name_coord_members, name_coord_counter
        ),
        "largest_normalized_name_only_groups": [
            {"normalized_name": key, "count": count}
            for key, count in normalized_name_counter.most_common(12)
            if count > 1
        ],
        "note": (
            "name equality is NOT entity identity; coordinate-rounded name keys "
            "are review candidates only. No records were dropped or merged."
        ),
    }

    report["encoding"] = {
        "decoded_as": "utf-8",
        "features_with_replacement_char_u+fffd": replacement_char_features,
        "features_with_control_chars": control_char_features,
        "features_with_non_ascii_name": non_ascii_name_features,
        "features_with_non_ascii_addr_stree": non_ascii_stree_features,
        "features_with_non_ascii_addr_ward": non_ascii_ward_features,
    }

    report["anomalies"] = {
        "processed_name_missing_or_blank": processed_name_missing_examples,
        "record_review_needed_count": len(features) - per_feature_structurally_valid,
    }

    report["provenance"] = {
        "top_level_metadata_keys": sorted(
            k for k in doc.keys() if k not in ("features",)
        ),
        "has_provenance_block": any(
            k in doc for k in ("provenance", "source", "metadata", "license", "retrieved_at")
        ),
        "feature_id_property_present": bool(id_like_keys),
        "note": (
            "no per-feature source identifier, retrieval time, URL or license "
            "field exists; collection time/source/OSM license/freshness are UNKNOWN"
        ),
    }

    report["features_total"] = len(features)
    return report


def main() -> int:
    try:  # keep Vietnamese vocabulary printable on Windows consoles
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geojson", type=Path, default=DEFAULT_GEOJSON)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    try:
        result = audit(args.geojson)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"audit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=False)
    if args.json_out:
        args.json_out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
