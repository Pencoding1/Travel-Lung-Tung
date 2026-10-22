"""Persistent local identity registry for the primary dataset.

The registry is the only mint of internal record ids. It is:

* namespaced (a foreign namespace can never reuse it);
* content-hash bound (it records the current and prior input revisions);
* immutable in normal operation (a re-run that changes nothing is a byte no-op);
* fail-closed (identity changes and changed source bytes require an explicit
  accepted revision; silent reidentification and silent history replacement are
  refused).

Every stored record is re-validated on load against the whole reverse/index
relation and against the existing canonical identity derivation. This is
internal consistency checking, NOT authenticated tamper protection.

Internal canonical ids reuse the existing acquisition ``stable_source_id``
helper applied to the local registry record id. They are clearly labelled as
internal; cross-export matching is NOT guaranteed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from crawler_service.app.acquisition.identity import stable_source_id
from crawler_service.app.acquisition.resolution import ConfigError
from crawler_service.app.acquisition.storage import atomic_write_bytes

from . import PRIMARY_NAMESPACE, INTERNAL_SOURCE_TYPE
from .identity import identity_key as build_identity_key

REGISTRY_VERSION = 1
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _serialize(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.match(value):
        raise ConfigError(f"registry {label} must be a lowercase 64-hex SHA256")
    return value


@dataclass
class IdentityPlan:
    """Resolved ids for the current run."""

    ids_by_identity_key: Dict[str, str]
    changed: bool


@dataclass
class IdentityRegistry:
    path: Path
    namespace: str = PRIMARY_NAMESPACE
    input_sha256: Optional[str] = None
    prior_input_sha256: List[str] = field(default_factory=list)
    next_sequence: int = 0
    records: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    identity_index: Dict[str, str] = field(default_factory=dict)
    existed: bool = False

    @classmethod
    def load(cls, path: Path, *, namespace: str = PRIMARY_NAMESPACE) -> "IdentityRegistry":
        path = Path(path)
        if not path.exists():
            return cls(path=path, namespace=namespace)
        try:
            document = json.loads(path.read_bytes().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConfigError(f"cannot read identity registry {path}: {exc}") from exc
        if not isinstance(document, dict):
            raise ConfigError(f"identity registry {path} must be a JSON object")
        stored_version = document.get("registry_version")
        if (
            isinstance(stored_version, bool)
            or not isinstance(stored_version, int)
            or stored_version != REGISTRY_VERSION
        ):
            raise ConfigError(
                f"identity registry {path} has unsupported registry_version "
                f"{stored_version!r}; refusing to reuse it"
            )
        stored_namespace = document.get("namespace")
        if stored_namespace != namespace:
            raise ConfigError(
                f"identity registry {path} is bound to namespace "
                f"{stored_namespace!r}, not {namespace!r}; refusing to reuse it for "
                "an unrelated dataset"
            )
        stored_source_type = document.get("source_type")
        if stored_source_type != INTERNAL_SOURCE_TYPE:
            raise ConfigError(
                f"identity registry {path} has unexpected source_type "
                f"{stored_source_type!r}"
            )
        if document.get("identity_scope") != "internal_local_only":
            raise ConfigError(
                f"identity registry {path} has unexpected identity_scope "
                f"{document.get('identity_scope')!r}; refusing to treat it as the "
                "reviewed local-only scope"
            )
        if document.get("cross_export_matching") != "not_guaranteed":
            raise ConfigError(
                f"identity registry {path} has unexpected cross_export_matching "
                f"{document.get('cross_export_matching')!r}; refusing to imply an "
                "unreviewed cross-export identity"
            )
        records = document.get("records")
        identity_index = document.get("identity_index")
        if not isinstance(records, dict) or not isinstance(identity_index, dict):
            raise ConfigError(f"identity registry {path} has malformed records/index")
        prior = document.get("prior_input_sha256", [])
        if not isinstance(prior, list):
            raise ConfigError(f"identity registry {path} has malformed prior_input_sha256")
        registry = cls(
            path=path,
            namespace=namespace,
            input_sha256=document.get("input_sha256"),
            prior_input_sha256=list(prior),
            next_sequence=document.get("next_sequence"),
            records=records,
            identity_index=identity_index,
            existed=True,
        )
        registry._validate()
        return registry

    def _validate(self) -> None:
        if self.input_sha256 is None:
            raise ConfigError(
                "registry must record a non-null input_sha256 for the current revision"
            )
        _require_sha256(self.input_sha256, "input_sha256")
        for index, value in enumerate(self.prior_input_sha256):
            _require_sha256(value, f"prior_input_sha256[{index}]")
        # prior_input_sha256 is ordered chronological history: repeats and the
        # current hash are legitimate (A->B->A->B), and history is never rewritten.
        if (
            isinstance(self.next_sequence, bool)
            or not isinstance(self.next_sequence, int)
            or self.next_sequence < 0
        ):
            raise ConfigError("registry next_sequence must be a non-negative integer")

        record_ids: Dict[str, str] = {}
        sequences: Dict[int, str] = {}
        indexed_ids: set = set()
        for identity_key, stable_id in self.identity_index.items():
            if not isinstance(identity_key, str) or not identity_key.strip():
                raise ConfigError("registry identity_index keys must be non-empty strings")
            if not isinstance(stable_id, str) or stable_id not in self.records:
                raise ConfigError(
                    f"registry index {identity_key!r} points to unknown id {stable_id!r} "
                    "(orphan index entry)"
                )
            if stable_id in indexed_ids:
                raise ConfigError(
                    f"registry id {stable_id!r} is claimed by two identity keys; "
                    "refusing a colliding registry (fail closed)"
                )
            indexed_ids.add(stable_id)

            record = self.records[stable_id]
            if not isinstance(record, dict):
                raise ConfigError(f"registry record {stable_id!r} must be an object")
            if record.get("identity_key") != identity_key:
                raise ConfigError(
                    f"registry record {stable_id!r} identity_key disagrees with the index"
                )

            record_id = record.get("record_id")
            if not isinstance(record_id, str) or not record_id.strip():
                raise ConfigError(f"registry record {stable_id!r} has no valid record_id")
            sequence = record.get("sequence")
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
                raise ConfigError(
                    f"registry record {stable_id!r} has an invalid sequence"
                )
            if record_id in record_ids:
                raise ConfigError(
                    f"registry record_id {record_id!r} is duplicated; refusing a "
                    "colliding registry (fail closed)"
                )
            record_ids[record_id] = stable_id
            if sequence in sequences:
                raise ConfigError(
                    f"registry sequence {sequence!r} is duplicated; refusing a "
                    "colliding registry (fail closed)"
                )
            sequences[sequence] = stable_id
            if record_id != f"r{sequence:06d}":
                raise ConfigError(
                    f"registry record {stable_id!r} record_id {record_id!r} does not "
                    f"match its sequence {sequence!r}"
                )
            if stable_source_id(INTERNAL_SOURCE_TYPE, record_id) != stable_id:
                raise ConfigError(
                    f"registry record {stable_id!r} does not match "
                    f"stable_source_id(record_id={record_id!r}); contradictory identity "
                    "metadata (fail closed)"
                )
            if "retired" in record and not isinstance(record["retired"], bool):
                raise ConfigError(
                    f"registry record {stable_id!r} 'retired' must be a boolean"
                )

            identity = record.get("identity")
            if not isinstance(identity, dict):
                raise ConfigError(f"registry record {stable_id!r} has no identity block")
            components = []
            for field_name in ("name_key", "coordinates", "address_anchor"):
                value = identity.get(field_name)
                if not isinstance(value, str):
                    raise ConfigError(
                        f"registry record {stable_id!r} identity.{field_name} must be "
                        "a string"
                    )
                components.append(value)
            expected_key = build_identity_key(*components)
            if expected_key != identity_key:
                raise ConfigError(
                    f"registry record {stable_id!r} identity components do not "
                    "reproduce its identity_key (fail closed)"
                )

        for stable_id in self.records:
            if stable_id not in indexed_ids:
                raise ConfigError(
                    f"registry record {stable_id!r} is not referenced by the identity "
                    "index (orphan record; fail closed)"
                )
        if sequences and self.next_sequence < max(sequences):
            raise ConfigError(
                "registry next_sequence is smaller than the highest assigned sequence"
            )

    def plan(
        self,
        identities: Mapping[str, Mapping[str, Any]],
        *,
        input_sha256: str,
        accept_input_revision: bool,
    ) -> IdentityPlan:
        """Resolve every identity key to an internal stable id, or fail closed.

        Any changed source bytes OR any identity addition/removal/component change
        requires an explicit ``accept_input_revision`` review. When accepted, the
        current hash is updated, the previous hash is appended to the ordered
        chronological history (repeats and returns to earlier bytes are legitimate),
        removed identities are retained and flagged ``retired`` (never erased), and
        the plan reports a real change. Identical bytes remain a true no-op.
        """

        if not self.existed:
            return self._assign_all(identities, input_sha256)

        _require_sha256(input_sha256, "input_sha256 (current run)")
        current_keys = set(identities)
        indexed = set(self.identity_index)
        active = {
            key
            for key in indexed
            if not self.records[self.identity_index[key]].get("retired")
        }
        retired = indexed - active
        added = current_keys - indexed
        reactivated = current_keys & retired
        removed = active - current_keys
        changed = {
            key
            for key in current_keys & active
            if self.records[self.identity_index[key]]["identity"] != dict(identities[key])
        }
        hash_changed = self.input_sha256 != input_sha256
        identity_changed = bool(added or reactivated or removed or changed)

        if (identity_changed or hash_changed) and not accept_input_revision:
            detail = []
            if hash_changed:
                detail.append("changed source bytes (sha256)")
            if added:
                detail.append(f"{len(added)} new identity key(s)")
            if reactivated:
                detail.append(f"{len(reactivated)} reactivated identity key(s)")
            if removed:
                detail.append(f"{len(removed)} removed identity key(s)")
            if changed:
                detail.append(f"{len(changed)} changed identity field set(s)")
            raise ConfigError(
                "identity registry review required before writing: "
                + ", ".join(detail)
                + "; re-run with an explicit accepted input revision"
            )

        if not identity_changed and not hash_changed:
            return IdentityPlan(
                ids_by_identity_key={key: self.identity_index[key] for key in current_keys},
                changed=False,
            )

        if hash_changed and self.input_sha256 is not None:
            self.prior_input_sha256.append(self.input_sha256)
        self.input_sha256 = input_sha256

        for key in sorted(removed):
            self.records[self.identity_index[key]]["retired"] = True
        for key in sorted(reactivated):
            record = self.records[self.identity_index[key]]
            record.pop("retired", None)
            if record["identity"] != dict(identities[key]):
                record["identity"] = dict(identities[key])
        for key in sorted(added):
            self._assign_identity(key, identities[key])
        for key in sorted(changed):
            self.records[self.identity_index[key]]["identity"] = dict(identities[key])

        return IdentityPlan(
            ids_by_identity_key={key: self.identity_index[key] for key in current_keys},
            changed=True,
        )

    def _assign_all(
        self, identities: Mapping[str, Mapping[str, Any]], input_sha256: str
    ) -> IdentityPlan:
        _require_sha256(input_sha256, "input_sha256 (current run)")
        self.input_sha256 = input_sha256
        for key in sorted(identities):
            self._assign_identity(key, identities[key])
        return IdentityPlan(
            ids_by_identity_key=dict(self.identity_index), changed=True
        )

    def _assign_identity(self, key: str, identity: Mapping[str, Any]) -> str:
        self.next_sequence += 1
        record_id = f"r{self.next_sequence:06d}"
        stable_id = stable_source_id(INTERNAL_SOURCE_TYPE, record_id)
        if stable_id in self.records:
            raise ConfigError(
                f"stable id collision for local record {record_id!r} (fail closed)"
            )
        self.records[stable_id] = {
            "record_id": record_id,
            "sequence": self.next_sequence,
            "identity_key": key,
            "identity": dict(identity),
        }
        self.identity_index[key] = stable_id
        return stable_id

    def document(self) -> Dict[str, Any]:
        return {
            "registry_version": REGISTRY_VERSION,
            "namespace": self.namespace,
            "source_type": INTERNAL_SOURCE_TYPE,
            "identity_scope": "internal_local_only",
            "cross_export_matching": "not_guaranteed",
            "input_sha256": self.input_sha256,
            "prior_input_sha256": list(self.prior_input_sha256),
            "next_sequence": self.next_sequence,
            "records": self.records,
            "identity_index": self.identity_index,
        }

    def render(self) -> bytes:
        """Canonical serialized registry bytes (used for conflict checks)."""

        return _serialize(self.document())

    def backup_path(self, prior_bytes: bytes) -> Path:
        """Immutable prior-registry evidence path bound to the full content digest."""

        digest = hashlib.sha256(prior_bytes).hexdigest()
        return self.path.with_name(f"{self.path.stem}.prior-{digest}{self.path.suffix}")

    def preflight(
        self, payload: Optional[bytes] = None, *, accept_input_revision: bool
    ) -> bool:
        """Validate the prospective registry without writing anything.

        Returns True when ``payload`` would change the registry bytes. Raises when
        the in-memory state is invalid, the supplied payload disagrees with that
        state, an explicit revision flag is missing, or the immutable backup path
        already holds different evidence. Direct save callers get the same checks.
        """

        payload = self.render() if payload is None else payload
        self._validate()
        expected = self.render()
        if payload != expected:
            raise ConfigError(
                "supplied registry payload disagrees with the validated in-memory "
                "registry state; refusing to bypass prospective validation"
            )
        existing = self.path.read_bytes() if self.path.exists() else None
        if existing == payload:
            return False
        if not self.existed and existing is not None:
            raise ConfigError(
                f"registry path {self.path} already exists but was not loaded as an "
                "existing registry; refusing to overwrite unvalidated state"
            )
        if self.existed:
            if not accept_input_revision:
                raise ConfigError(
                    "refusing to persist a changed identity registry without an "
                    "explicitly accepted input revision"
                )
            if existing is None:
                raise ConfigError(
                    f"existing identity registry {self.path} disappeared before it "
                    "could be preserved as revision evidence"
                )
            backup = self.backup_path(existing)
            if backup.exists():
                if not backup.is_file() or backup.read_bytes() != existing:
                    raise ConfigError(
                        f"refusing to overwrite prior-registry backup {backup} with "
                        "different evidence"
                    )
        return True

    def save(self, payload: Optional[bytes] = None, *, accept_input_revision: bool) -> bool:
        """Atomically persist the registry; return True when bytes changed.

        All validation and backup-collision checks happen before the first write.
        The previous registry is preserved under a filename bound to the full
        SHA256 of its content, so a repeated source hash with different registry
        history can never collide with or overwrite earlier evidence. Existing
        backups are retained; nothing is cleaned up automatically.
        """

        changed = self.preflight(payload, accept_input_revision=accept_input_revision)
        if not changed:
            return False
        rendered = self.render() if payload is None else payload
        existing = self.path.read_bytes() if self.path.exists() else None
        if self.existed and existing is not None:
            backup = self.backup_path(existing)
            if not backup.exists():
                atomic_write_bytes(backup, existing, overwrite=False)
        atomic_write_bytes(self.path, rendered, overwrite=True)
        return True
