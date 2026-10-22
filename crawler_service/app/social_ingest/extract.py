"""Deterministic, dependency-free extraction for public web POI sources.

Two structured routes are supported:

* JSON-LD (``LocalBusiness``/``ItemList`` and compatible business objects);
* a declared HTML source profile (the ``ac-chapter`` chapter layout used by
  vietnam.travel article pages).

A public CSV route exists for genuinely public tables. There is no LLM, no
browser DOM and no heuristic merging: each record is extracted from its own
structural block, so a name from one block can never be paired with an address
from another.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

_WHITESPACE_RE = re.compile(r"\s+")
_ADDRESS_RE = re.compile(
    r"Address\s*:\s*(.+?)(?=\s*(?:Hours of Operation|Opening Hours|Admission)\s*:|$)",
    re.IGNORECASE,
)
_HOURS_RE = re.compile(
    r"(?:Hours of Operation|Opening Hours)\s*:\s*(.+?)(?=\s*(?:Address|Admission)\s*:|$)",
    re.IGNORECASE,
)
_DISTRICT_RE = re.compile(
    r"\b(District\s+\d+|Quận\s+\d+|Huyện\s+[A-Za-zÀ-ỹ ]+?)(?=,|$)",
    re.IGNORECASE,
)

_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}


def normalize_ws(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value or "").strip()


@dataclass
class Node:
    tag: str
    attrs: Dict[str, str] = field(default_factory=dict)
    children: List[Union["Node", str]] = field(default_factory=list)

    @property
    def classes(self) -> List[str]:
        return (self.attrs.get("class") or "").split()


class _DomBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document")
        self._stack: List[Node] = [self.root]

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        node = Node(
            tag.lower(),
            {key.lower(): (value if value is not None else "") for key, value in attrs},
        )
        self._stack[-1].children.append(node)
        if tag.lower() not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS and self._stack[-1].tag == tag.lower():
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        target = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == target:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self._stack[-1].tag in ("script", "style"):
            return
        if data:
            self._stack[-1].children.append(data)


def parse_html(html: str) -> Node:
    builder = _DomBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


def walk(node: Node) -> Iterable[Node]:
    for child in node.children:
        if isinstance(child, Node):
            yield child
            yield from walk(child)


def find_all(root: Node, *, tag: Optional[str] = None, cls: Optional[str] = None) -> List[Node]:
    found: List[Node] = []
    for node in walk(root):
        if tag is not None and node.tag != tag:
            continue
        if cls is not None and cls not in node.classes:
            continue
        found.append(node)
    return found


def find_first(root: Node, *, tag: Optional[str] = None, cls: Optional[str] = None) -> Optional[Node]:
    for node in walk(root):
        if tag is not None and node.tag != tag:
            continue
        if cls is not None and cls not in node.classes:
            continue
        return node
    return None


def node_text(node: Node) -> str:
    parts: List[str] = []

    def visit(current: Node) -> None:
        for child in current.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag not in ("script", "style"):
                visit(child)

    visit(node)
    return normalize_ws(" ".join(parts))


@dataclass
class ExtractedRecord:
    """A raw, source-derived record before minimum/identity validation."""

    record_id: Optional[str]
    name: Optional[str]
    address_raw: Optional[str]
    description: Optional[str]
    review_text: Optional[str]
    category_tags: List[str]
    coordinates: Optional[Tuple[float, float]]
    opening_hours_raw: Optional[str]
    field_evidence: List[Dict[str, Any]]
    page_url: str
    page_capture_sha256: str
    page_capture_path: str
    page_fetched_at: str
    locator: str
    issues: List[str] = field(default_factory=list)
    address_hints_extra: Dict[str, str] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    records: List[ExtractedRecord]
    errors: List[Dict[str, str]]


_BUSINESS_TYPES = {
    "localbusiness", "restaurant", "cafeorcoffeeshop", "touristattraction",
    "museum", "lodgingbusiness", "store", "barorpub", "bakery",
    "foodestablishment", "place",
}

_JSONLD_SCRIPT_RE = re.compile(
    r"<script[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def _extract_jsonld_blocks(html: str) -> Tuple[List[Any], List[Dict[str, str]]]:
    documents: List[Any] = []
    errors: List[Dict[str, str]] = []
    for index, match in enumerate(_JSONLD_SCRIPT_RE.finditer(html)):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            documents.append(json.loads(raw))
        except ValueError as exc:
            errors.append({"locator": f"script[type=application/ld+json][{index}]", "error": f"malformed_jsonld: {exc}"})
    return documents, errors


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _types(value: Any) -> List[str]:
    return [str(item).lower() for item in _as_list(value) if isinstance(item, (str, int))]


def _business_objects(value: Any, locator: str) -> Iterable[Tuple[Dict[str, Any], str, List[str]]]:
    """Yield (object, locator, inherited_category_tags) for ItemList/business."""

    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _business_objects(item, f"{locator}[{index}]")
        return
    if not isinstance(value, dict):
        return
    types = _types(value.get("@type"))
    if "itemlist" in types:
        for index, item in enumerate(_as_list(value.get("itemListElement"))):
            wrapped = item
            if isinstance(item, dict) and isinstance(item.get("item"), dict):
                wrapped = item["item"]
            yield from _business_objects(
                wrapped, f"{locator}/itemListElement/{index}"
            )
        return
    if isinstance(value.get("@graph"), list):
        yield from _business_objects(value["@graph"], f"{locator}/@graph")
        return
    if any(t in _BUSINESS_TYPES for t in types):
        category_tags = [f"schema:{t}" for t in types if t in _BUSINESS_TYPES]
        yield value, locator, category_tags


def _jsonld_address(value: Any) -> Dict[str, str]:
    if isinstance(value, str):
        return {"addr:full": normalize_ws(value)}
    if not isinstance(value, dict):
        return {}
    hints: Dict[str, str] = {}
    street = normalize_ws(str(value.get("streetAddress") or ""))
    district = normalize_ws(str(value.get("addressLocality") or ""))
    region = normalize_ws(str(value.get("addressRegion") or ""))
    country = normalize_ws(str(value.get("addressCountry") or ""))
    parts = [part for part in (street, district, region) if part]
    if parts:
        hints["addr:full"] = ", ".join(parts)
    if district:
        hints["addr:district_raw"] = district
    if region:
        hints["addr:region_raw"] = region
    if country:
        hints["addr:country_raw"] = country
    return hints


def _jsonld_coordinates(value: Any) -> Optional[Tuple[float, float]]:
    if not isinstance(value, dict):
        return None
    lat, lon = value.get("latitude"), value.get("longitude")
    if (
        isinstance(lat, (int, float)) and not isinstance(lat, bool)
        and isinstance(lon, (int, float)) and not isinstance(lon, bool)
    ):
        return (float(lat), float(lon))
    return None


def extract_jsonld(
    html: str,
    *,
    page_url: str,
    capture_sha256: str,
    capture_path: str,
    fetched_at: str,
) -> ExtractionResult:
    documents, errors = _extract_jsonld_blocks(html)
    records: List[ExtractedRecord] = []
    for document_index, document in enumerate(documents):
        for obj, locator, category_tags in _business_objects(
            document, f"/ld[{document_index}]"
        ):
            name = normalize_ws(str(obj.get("name") or "")) or None
            address_hints = _jsonld_address(obj.get("address"))
            description = normalize_ws(str(obj.get("description") or "")) or None
            review_text = _first_review(obj)
            review_value = normalize_ws(review_text) if review_text else None
            if name is None and not address_hints and not description:
                continue
            record_id = obj.get("@id") or obj.get("url")
            if not isinstance(record_id, str) or not record_id.strip():
                record_id = None
            coordinates = _jsonld_coordinates(obj.get("geo"))
            opening = obj.get("openingHours")
            if isinstance(opening, list):
                opening_raw = "; ".join(
                    normalize_ws(str(item)) for item in opening if str(item).strip()
                ) or None
            elif isinstance(opening, str) and opening.strip():
                opening_raw = normalize_ws(opening)
            else:
                opening_raw = None

            evidence: List[Dict[str, Any]] = [
                _evidence("name", name, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/name"),
                _evidence("address_raw", address_hints.get("addr:full"), page_url, fetched_at, capture_path, capture_sha256, f"{locator}/address"),
                _evidence("description", description, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/description"),
                _evidence("review_text", review_value, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/review"),
                _evidence("opening_hours_raw", opening_raw, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/openingHours"),
            ]
            records.append(
                ExtractedRecord(
                    record_id=record_id,
                    name=name,
                    address_raw=address_hints.get("addr:full"),
                    description=description,
                    review_text=review_value,
                    category_tags=category_tags,
                    coordinates=coordinates,
                    opening_hours_raw=opening_raw,
                    field_evidence=[item for item in evidence if item["value"] is not None],
                    page_url=page_url,
                    page_capture_sha256=capture_sha256,
                    page_capture_path=capture_path,
                    page_fetched_at=fetched_at,
                    locator=locator,
                    address_hints_extra={
                        key: value
                        for key, value in address_hints.items()
                        if key != "addr:full"
                    },
                )
            )
    return ExtractionResult(records=records, errors=errors)


def _first_review(obj: Dict[str, Any]) -> Optional[str]:
    for candidate in _as_list(obj.get("review")) + _as_list(obj.get("reviews")):
        if isinstance(candidate, dict):
            for key in ("reviewBody", "description", "text"):
                value = candidate.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        elif isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _evidence(
    field_name: str,
    value: Optional[str],
    page_url: str,
    fetched_at: str,
    capture_path: str,
    capture_sha256: str,
    locator: str,
) -> Dict[str, Any]:
    return {
        "field": field_name,
        "value": value,
        "source_url": page_url,
        "fetched_at": fetched_at,
        "raw_capture_path": capture_path,
        "raw_sha256": capture_sha256,
        "locator": locator,
    }


def extract_html_chapters(
    html: str,
    *,
    page_url: str,
    capture_sha256: str,
    capture_path: str,
    fetched_at: str,
    page_slug: str,
    category_tags: Sequence[str] = ("tourism=attraction",),
) -> ExtractionResult:
    """Extract ``section.ac-chapter`` blocks (vietnam.travel article layout).

    The stable anchor is the authored ``id`` attribute of the section (e.g.
    ``chapter-1``), combined with the page slug. It is never an array index and
    never the mutable name/address.
    """

    dom = parse_html(html)
    records: List[ExtractedRecord] = []
    sections = find_all(dom, tag="section", cls="ac-chapter")
    for section_index, section in enumerate(sections):
        anchor = (section.attrs.get("id") or "").strip() or None
        heading = find_first(section, tag="h2")
        body = find_first(section, cls="ac-body")
        name = node_text(heading) if heading else None
        body_text = node_text(body) if body else ""
        address_match = _ADDRESS_RE.search(body_text)
        hours_match = _HOURS_RE.search(body_text)
        address_raw = normalize_ws(address_match.group(1)) if address_match else None
        hours_raw = normalize_ws(hours_match.group(1)) if hours_match else None

        # Narrative is the text before the first structured label; it never
        # absorbs the address/hours of the block.
        cut_points = [
            body_text.lower().find(marker)
            for marker in ("admission:", "hours of operation:", "opening hours:", "address:")
            if body_text.lower().find(marker) >= 0
        ]
        description = normalize_ws(body_text[: min(cut_points)]) if cut_points else normalize_ws(body_text)
        description = description or None

        locator = f"section.ac-chapter[{section_index}]" + (
            f"#{anchor}" if anchor else ""
        )
        if name is None:
            issues = ["missing_name"]
        else:
            issues = []
        if address_raw is None:
            issues.append("missing_address")
        if description is None:
            issues.append("missing_description")
        if anchor is None:
            issues.append("unstable_record_anchor")

        evidence = [
            _evidence("name", name, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/h2"),
            _evidence("address_raw", address_raw, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/div.ac-body"),
            _evidence("description", description, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/div.ac-body"),
            _evidence("opening_hours_raw", hours_raw, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/div.ac-body"),
        ]
        records.append(
            ExtractedRecord(
                record_id=(f"{page_slug}#{anchor}" if anchor and page_slug else None),
                name=name,
                address_raw=address_raw,
                description=description,
                review_text=None,
                category_tags=list(category_tags),
                coordinates=None,
                opening_hours_raw=hours_raw,
                field_evidence=[item for item in evidence if item["value"] is not None],
                page_url=page_url,
                page_capture_sha256=capture_sha256,
                page_capture_path=capture_path,
                page_fetched_at=fetched_at,
                locator=locator,
                issues=issues,
            )
        )
    return ExtractionResult(records=records, errors=[])


def address_hints(address_raw: Optional[str]) -> Dict[str, str]:
    hints: Dict[str, str] = {}
    if not address_raw:
        return hints
    hints["addr:full"] = address_raw
    match = _DISTRICT_RE.search(address_raw)
    if match:
        hints["addr:district_raw"] = normalize_ws(match.group(1))
    lowered = address_raw.casefold()
    if "ho chi minh" in lowered or "hồ chí minh" in lowered or "tp.hcm" in lowered:
        hints["addr:city_raw"] = "Ho Chi Minh City"
    return hints


def extract_csv(
    payload: bytes,
    *,
    page_url: str,
    capture_sha256: str,
    capture_path: str,
    fetched_at: str,
    category_tags: Sequence[str] = (),
) -> ExtractionResult:
    """Parse a public CSV table (UTF-8 with optional BOM, quotes, newlines).

    A stable row identity is required from an explicit ``id`` or ``url``
    column. The row ordinal is never used as identity.
    """

    errors: List[Dict[str, str]] = []
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return ExtractionResult([], [{"locator": "csv", "error": f"not_utf8: {exc}"}])
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames:
        return ExtractionResult([], [{"locator": "csv", "error": "missing_header"}])
    header = {(name or "").strip().lower(): name for name in reader.fieldnames}
    if "name" not in header:
        return ExtractionResult([], [{"locator": "csv", "error": "missing_name_column"}])

    records: List[ExtractedRecord] = []
    for row_number, row in enumerate(reader, start=2):
        def get(key: str) -> Optional[str]:
            column = header.get(key)
            if column is None:
                return None
            value = row.get(column)
            return value if isinstance(value, str) and value.strip() else None

        name = normalize_ws(get("name") or "") or None
        address_raw = normalize_ws(get("address") or "") or None
        description = normalize_ws(get("description") or "") or None
        review_text = normalize_ws(get("review") or "") or None
        if not any((name, address_raw, description, review_text)):
            continue
        record_id = get("id") or get("url")
        record_id = record_id.strip() if record_id else None
        coordinates = None
        lat, lon = get("latitude"), get("longitude")
        if lat is not None and lon is not None:
            try:
                coordinates = (float(lat), float(lon))
            except ValueError:
                errors.append({"locator": f"csv.row[{row_number}]", "error": "invalid_coordinates"})
        issues: List[str] = []
        if name is None:
            issues.append("missing_name")
        if address_raw is None:
            issues.append("missing_address")
        if description is None and review_text is None:
            issues.append("missing_description")
        if record_id is None:
            issues.append("unstable_record_anchor")
        locator = f"csv.rows[id={record_id}]" if record_id else f"csv.row[{row_number}]"
        evidence = [
            _evidence("name", name, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/name"),
            _evidence("address_raw", address_raw, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/address"),
            _evidence("description", description, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/description"),
            _evidence("review_text", review_text, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/review"),
        ]
        records.append(
            ExtractedRecord(
                record_id=record_id,
                name=name,
                address_raw=address_raw,
                description=description,
                review_text=review_text,
                category_tags=list(category_tags),
                coordinates=coordinates,
                opening_hours_raw=None,
                field_evidence=[item for item in evidence if item["value"] is not None],
                page_url=page_url,
                page_capture_sha256=capture_sha256,
                page_capture_path=capture_path,
                page_fetched_at=fetched_at,
                locator=locator,
                issues=issues,
            )
        )
    return ExtractionResult(records=records, errors=errors)


# --- Wikivoyage article listings (CC BY-SA) --------------------------------
#
# Wikivoyage renders every point of interest as one ``vcard`` listing block with
# the authored ``listing-name`` / ``listing-address`` / ``listing-content``
# children. Each block is parsed on its own, so a name can never be paired with
# the address of the next listing. Nothing is inferred: a block without an
# address keeps ``missing_address`` instead of borrowing one from the body text,
# and a marker that does not parse yields no coordinates at all.

_GEO_TEXT_CLASSES = ("listing-geo", "geo")
_GEO_NUMBER_RE = re.compile(r"^([+-]?\d+(?:\.\d+)?)\s*([NSEW])?$", re.IGNORECASE)
_GEO_PAIR_SPLIT_RE = re.compile(r"[;,]")


def _descendants(node: Node):
    yield from walk(node)


def _first_by_class(node: Node, classes: Sequence[str]) -> Optional[Node]:
    for child in _descendants(node):
        if any(name in child.classes for name in classes):
            return child
    return None


def _parse_geo_pair(text: str) -> Optional[Tuple[float, float]]:
    """Parse a ``lat; lon`` / ``lat, lon`` marker, with optional N/S/E/W."""

    cleaned = normalize_ws((text or "").replace("°", " "))
    if not cleaned:
        return None
    parts = [part.strip() for part in _GEO_PAIR_SPLIT_RE.split(cleaned) if part.strip()]
    if len(parts) != 2:
        return None
    values: List[float] = []
    for part in parts:
        match = _GEO_NUMBER_RE.match(part)
        if match is None:
            return None
        value = float(match.group(1))
        hemisphere = (match.group(2) or "").upper()
        if hemisphere in ("S", "W"):
            value = -abs(value)
        values.append(value)
    latitude, longitude = values
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return None
    return (latitude, longitude)


def _wikivoyage_coordinates(card: Node) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
    """Return ``(coordinates, unparsed_marker_text)`` for one listing block.

    The two marker forms Wikivoyage emits are honoured: the ``listing-geo`` /
    ``geo`` microformat text and the ``data-lat``/``data-lon`` pair. A marker
    that exists but cannot be parsed is reported, never rounded or guessed.
    """

    for child in _descendants(card):
        lat = (child.attrs.get("data-lat") or "").strip()
        lon = (child.attrs.get("data-lon") or "").strip()
        if lat and lon:
            pair = _parse_geo_pair(f"{lat};{lon}")
            return (pair, None) if pair is not None else (None, f"{lat};{lon}")
    for class_name in _GEO_TEXT_CLASSES:
        element = _first_by_class(card, (class_name,))
        if element is None:
            continue
        text = node_text(element)
        if not text:
            continue
        pair = _parse_geo_pair(text)
        return (pair, None) if pair is not None else (None, text)
    return None, None


def extract_wikivoyage_listings(
    html: str,
    *,
    page_url: str,
    capture_sha256: str,
    capture_path: str,
    fetched_at: str,
    page_slug: str,
    category_tags: Sequence[str] = ("tourism=attraction",),
) -> ExtractionResult:
    """Extract ``div.vcard`` listing blocks from a Wikivoyage article page.

    The stable anchor is the listing's authored HTML ``id`` (on the ``vcard``
    block, or on its ``listing-name`` element), combined with the page slug --
    never the array index, the name or the address. A listing without any
    authored id keeps ``record_id=None`` and ``unstable_record_anchor``, so it
    can never be accepted under a mutable identity.

    Only source-derived fields are filled: name, address, description (the
    listing body), coordinates when a marker is present, and per-field evidence
    pointing at this page's capture. Category tags come from the declared
    profile, not from a guess about the section heading.
    """

    dom = parse_html(html)
    records: List[ExtractedRecord] = []
    errors: List[Dict[str, str]] = []
    cards = [node for node in walk(dom) if "vcard" in node.classes]
    for card_index, card in enumerate(cards):
        name_node = _first_by_class(card, ("listing-name",))
        name = node_text(name_node) if name_node is not None else ""
        name = name or None

        address_node = _first_by_class(card, ("listing-address",))
        if address_node is None:
            address_node = next(
                (child for child in _descendants(card) if child.tag == "address"), None
            )
        address_raw = node_text(address_node) if address_node is not None else ""
        address_raw = address_raw or None

        content_node = _first_by_class(card, ("listing-content",))
        description = node_text(content_node) if content_node is not None else ""
        description = description or None

        anchor = (card.attrs.get("id") or "").strip() or None
        if anchor is None and name_node is not None:
            anchor = (name_node.attrs.get("id") or "").strip() or None

        coordinates, unparsed = _wikivoyage_coordinates(card)
        locator = f"div.vcard[{card_index}]" + (f"#{anchor}" if anchor else "")
        if unparsed is not None:
            errors.append(
                {"locator": locator, "error": f"invalid_coordinates: {unparsed!r}"}
            )

        issues: List[str] = []
        if name is None:
            issues.append("missing_name")
        if address_raw is None:
            issues.append("missing_address")
        if description is None:
            issues.append("missing_description")
        if anchor is None:
            issues.append("unstable_record_anchor")

        evidence = [
            _evidence("name", name, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/listing-name"),
            _evidence("address_raw", address_raw, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/listing-address"),
            _evidence("description", description, page_url, fetched_at, capture_path, capture_sha256, f"{locator}/listing-content"),
        ]
        records.append(
            ExtractedRecord(
                record_id=(f"{page_slug}#{anchor}" if anchor and page_slug else None),
                name=name,
                address_raw=address_raw,
                description=description,
                review_text=None,
                category_tags=list(category_tags),
                coordinates=coordinates,
                opening_hours_raw=None,
                field_evidence=[item for item in evidence if item["value"] is not None],
                page_url=page_url,
                page_capture_sha256=capture_sha256,
                page_capture_path=capture_path,
                page_fetched_at=fetched_at,
                locator=locator,
                issues=issues,
            )
        )
    return ExtractionResult(records=records, errors=errors)


def page_slug(url: str) -> str:
    """Stable, non-name page token from the URL path."""

    from urllib.parse import urlsplit

    path = urlsplit(url).path.strip("/")
    return path.casefold() or "index"
