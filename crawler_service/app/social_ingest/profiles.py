"""Declared source profiles and their official-policy status.

A profile is deliberately small: one publisher/host, a bounded number of
content URLs, one deterministic extractor, and the observed policy evidence.
Unknown or restrictive reuse terms are recorded as such; they are never turned
into permission. A profile whose reuse is not explicitly ``permitted`` is
refused by the fetch gate (``gate_for_profile``/``gate_for_hosts``) before any
request is sent, so it yields no captured content and no accepted POI at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

# Allowed reuse statuses. Only ``permitted`` may ever flow past the policy gate.
REUSE_PERMITTED = "permitted"
REUSE_NOT_PERMITTED = "not_permitted"
REUSE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceProfile:
    name: str
    source_id: str
    dataset: str
    host: str
    allow_hosts: Tuple[str, ...]
    start_urls: Tuple[str, ...]
    extractor: str
    category_tags: Tuple[str, ...]
    license: str
    reuse_status: str
    policy_evidence: Tuple[str, ...] = ()
    notes: str = ""
    max_content_urls: int = 6
    extra: Dict[str, str] = field(default_factory=dict)
    #: Reuse is granted *conditionally*: every affected artifact must carry the
    #: publisher's attribution notice. Declared here so the obligation is data,
    #: not prose in a docstring -- the runner refuses to export a profile that
    #: sets this flag without a notice.
    attribution_required: bool = False
    attribution_text: str = ""
    #: True when the license imposes share-alike on derived/combined text.
    share_alike: bool = False

    def __post_init__(self) -> None:
        if self.reuse_status not in (REUSE_PERMITTED, REUSE_NOT_PERMITTED, REUSE_UNKNOWN):
            raise ValueError(f"invalid reuse_status: {self.reuse_status!r}")
        if len(self.start_urls) > self.max_content_urls:
            raise ValueError("profile exceeds its content URL budget")
        if self.extractor not in (
            "html_chapters_v1", "jsonld_v1", "csv_v1", "wikivoyage_listings_v1",
        ):
            raise ValueError(f"unknown extractor: {self.extractor!r}")
        if self.attribution_required and not self.attribution_text.strip():
            raise ValueError(
                "attribution_required profile must declare a non-empty attribution_text"
            )


VIETNAM_TRAVEL_HCMC7 = SourceProfile(
    name="vietnam_travel_hcmc7",
    source_id="vietnam-travel-node137",
    dataset="social_web_oc050",
    host="vietnam.travel",
    allow_hosts=("vietnam.travel",),
    start_urls=("https://vietnam.travel/node/137",),
    extractor="html_chapters_v1",
    category_tags=("tourism=attraction",),
    license="UNKNOWN",
    reuse_status=REUSE_NOT_PERMITTED,
    policy_evidence=(
        "data/social_expansion_20261018/real/policy/vietnam_travel_robots.txt",
        "data/social_expansion_20261018/real/policy/vietnam_travel_terms.html",
    ),
    notes=(
        "Robots fetched 2026-10-18 (HTTP 200) does not disallow /node/137. "
        "Terms page (redirect /terms-conditions -> /term-conditions, HTTP 200) "
        "states that except with prior written permission the material may not "
        "be stored or reproduced. Reuse is therefore NOT permitted; all records "
        "are quarantined for policy review. No license was inferred."
    ),
)

#: Wikivoyage article text: CC BY-SA 4.0 -- reuse is permitted *with*
#: attribution and share-alike, which is the strongest obligation of any source
#: declared here. The notice below is the default rendering of that obligation.
WIKIVOYAGE_LICENSE = "CC-BY-SA-4.0"
WIKIVOYAGE_LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
WIKIVOYAGE_ATTRIBUTION = (
    "Text from Wikivoyage (en.wikivoyage.org), (c) Wikivoyage contributors, "
    "licensed CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). "
    "Keep this notice and the source page URL; adaptations stay CC BY-SA 4.0."
)

WIKIVOYAGE_EN_HCMC = SourceProfile(
    name="wikivoyage_en_hcmc",
    source_id="wikivoyage-en-hcmc",
    dataset="social_web_oc050",
    host="en.wikivoyage.org",
    allow_hosts=("en.wikivoyage.org",),
    start_urls=("https://en.wikivoyage.org/wiki/Ho_Chi_Minh_City",),
    extractor="wikivoyage_listings_v1",
    # The listing heading Wikivoyage uses (See/Do/Eat/Drink/Sleep) is not
    # converted into a POI category here: that is a review decision, so every
    # record stays untagged and is flagged ``unknown_category`` downstream
    # instead of being labelled an attraction without evidence.
    category_tags=(),
    license=WIKIVOYAGE_LICENSE,
    reuse_status=REUSE_PERMITTED,
    attribution_required=True,
    attribution_text=WIKIVOYAGE_ATTRIBUTION,
    share_alike=True,
    policy_evidence=(
        "docs/project/handoffs/OC-050/source-review-addendum.md",
    ),
    notes=(
        "Reviewed 2026-10-18 in the OC-050 source addendum: article text is "
        "CC BY-SA 4.0 with explicit attribution and share-alike obligations "
        "(https://en.wikivoyage.org/wiki/Wikivoyage:Copyleft), and "
        "https://en.wikivoyage.org/robots.txt welcomes low-speed article bots "
        "while disallowing /w/, /api/ and /Special. Only the plain /wiki/ article "
        "path is declared. Reuse is permitted WITH attribution: every exported "
        "record and source block carries the notice, and share_alike is declared "
        "true. No live request was made while adding this profile, so no raw "
        "policy capture exists yet; the first approved --fetch run must store "
        "robots.txt and the licence page alongside the content capture. The "
        "listing selectors (vcard/listing-name/listing-address/listing-content) "
        "follow the documented Wikivoyage listing rendering and still have to be "
        "confirmed against real bytes. Address and admin review remain gates."
    ),
)

_PROFILES: Dict[str, SourceProfile] = {
    VIETNAM_TRAVEL_HCMC7.name: VIETNAM_TRAVEL_HCMC7,
    WIKIVOYAGE_EN_HCMC.name: WIKIVOYAGE_EN_HCMC,
}


def get_profile(name: str) -> SourceProfile:
    try:
        return _PROFILES[name]
    except KeyError as exc:
        raise KeyError(f"unknown source profile: {name!r}") from exc


def list_profiles() -> Dict[str, SourceProfile]:
    return dict(_PROFILES)


def policy_allows_reuse(profile: SourceProfile) -> bool:
    """Only an explicitly reviewed ``permitted`` status passes the gate."""

    return profile.reuse_status == REUSE_PERMITTED


#: Machine-readable refusal codes. ``permitted`` never maps to a code.
REUSE_BLOCK_REASONS: Dict[str, str] = {
    REUSE_NOT_PERMITTED: "license_reuse_not_permitted",
    REUSE_UNKNOWN: "license_reuse_unknown",
}


@dataclass(frozen=True)
class ReuseGate:
    """Why a declared source may not be fetched. Returned as ``None`` when ok."""

    reason: str
    profile: str
    source_id: str
    host: str
    reuse_status: str

    def detail(self) -> str:
        return (
            f"{self.profile} ({self.source_id}) "
            f"reuse_status={self.reuse_status}"
        )


def gate_for_profile(profile: SourceProfile) -> Optional[ReuseGate]:
    """Refusal for one declared profile, or ``None`` when reuse is permitted."""

    reason = REUSE_BLOCK_REASONS.get(profile.reuse_status)
    if reason is None:
        return None
    return ReuseGate(
        reason=reason,
        profile=profile.name,
        source_id=profile.source_id,
        host=profile.host,
        reuse_status=profile.reuse_status,
    )


def gate_for_hosts(hosts) -> Optional[ReuseGate]:
    """Refusal derived from allowlisted hosts alone.

    Conservative on purpose: a fetcher built by a caller that only knows the
    host (the CLI builds fetchers this way) still cannot reach a declared
    restrictive source. Hosts with no declared profile pass — their terms are
    simply not declared here.
    """

    normalized = {str(host).lower().rstrip(".") for host in hosts}
    for profile in _PROFILES.values():
        if profile.host.lower().rstrip(".") in normalized:
            gate = gate_for_profile(profile)
            if gate is not None:
                return gate
    return None
