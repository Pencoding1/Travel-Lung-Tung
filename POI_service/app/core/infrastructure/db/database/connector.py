import os
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace

from neo4j import GraphDatabase
from app.core.config.settings import MemgraphDB, db_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Firestore enablement
#
# Graph-only is the default: Firebase/Firestore is only touched when the
# operator explicitly enables it. The accepted spellings are documented here
# (and in docs/decisions/009-optional-firestore.md) so the flag is not
# interpreted loosely.
# ---------------------------------------------------------------------------
FIRESTORE_ENABLED_ENV = "FIRESTORE_ENABLED"

_TRUE_TOKENS = frozenset({"true", "1", "yes", "on"})
_FALSE_TOKENS = frozenset({"false", "0", "no", "off"})


def parse_firestore_enabled(raw: "str | None") -> bool:
    """Strictly parse the ``FIRESTORE_ENABLED`` flag.

    - absent / blank  -> ``False`` (graph-only default)
    - true  spellings : ``true``, ``1``, ``yes``, ``on`` (case-insensitive)
    - false spellings : ``false``, ``0``, ``no``, ``off`` (case-insensitive)

    Any other value is invalid configuration and raises :class:`ValueError`; it
    is never silently treated as disabled.
    """
    if raw is None or raw.strip() == "":
        return False
    token = raw.strip().lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    raise ValueError(
        f"Invalid {FIRESTORE_ENABLED_ENV} value; expected one of "
        "true/false/1/0/yes/no/on/off (unset means graph-only)."
    )


def firestore_enabled() -> bool:
    """Read ``FIRESTORE_ENABLED`` from the process environment."""
    return parse_firestore_enabled(os.getenv(FIRESTORE_ENABLED_ENV))


def _load_firebase_sdk() -> SimpleNamespace:
    """Import the Firebase Admin SDK lazily.

    This is the *only* place ``firebase_admin`` is imported. It is called from
    :meth:`FireStoreConnector.connect` and therefore never runs in graph-only
    mode, so such a deployment needs neither the package nor credentials.
    """
    from firebase_admin import (
        credentials,
        firestore,
        initialize_app,
        delete_app,
        auth,
        _apps,
    )

    return SimpleNamespace(
        credentials=credentials,
        firestore=firestore,
        initialize_app=initialize_app,
        delete_app=delete_app,
        auth=auth,
        _apps=_apps,
    )


class FireStoreConnector:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FireStoreConnector, cls).__new__(cls)
            cls._instance._reset_state()
        return cls._instance

    def __init__(self, sdk_loader=None, key_path=None):
        # __init__ runs on every construction of the singleton; only apply the
        # explicit overrides so an active connection is never silently reset.
        if sdk_loader is not None:
            self._sdk_loader = sdk_loader
        if key_path is not None:
            self._key_path = Path(key_path)

    def _reset_state(self) -> None:
        # FAST INIT: declare state only. No imports, no network, no credentials.
        self.db = None
        self._initialized = False
        self._owned_app = None
        self._sdk = None
        self._sdk_loader = _load_firebase_sdk
        self._key_path = None

    @property
    def is_ready(self) -> bool:
        return self._initialized and self.db is not None

    def _service_account_key_path(self) -> Path:
        if self._key_path is not None:
            return self._key_path
        root_dir = Path(__file__).resolve().parents[4]
        return root_dir / "secrets" / "serviceAccountKey.json"

    def connect(self, enabled: "bool | None" = None) -> None:
        """Initialize Firestore only when explicitly enabled.

        ``enabled=None`` reads ``FIRESTORE_ENABLED``. Disabled is a no-op that
        never imports ``firebase_admin`` nor looks for credentials.
        """
        if enabled is None:
            enabled = firestore_enabled()
        if not enabled:
            logger.info(
                "Firestore disabled (graph-only mode); skipping Firebase initialization."
            )
            return
        if self._initialized:
            return

        sdk = self._sdk_loader()
        # Record the SDK before initializing so a failure part-way through can
        # still release an application this connector created.
        self._sdk = sdk
        try:
            if not sdk._apps:
                key_path = self._service_account_key_path()
                if not key_path.exists():
                    raise FileNotFoundError(
                        "Firestore service account key file is missing."
                    )
                cred = sdk.credentials.Certificate(str(key_path))
                self._owned_app = sdk.initialize_app(cred)

            self.db = sdk.firestore.client()
            self._initialized = True
            logger.info("Firebase/Firestore connected successfully.")
        except Exception as exc:
            # Sanitized: never log the raw credential/provider message.
            logger.error("Firestore initialization failed (%s).", type(exc).__name__)
            self.close()
            raise

    def verify_connectivity(self) -> bool:
        if not self._initialized or self.db is None or self._sdk is None:
            return False
        try:
            self._sdk.auth.list_users(max_results=1)
            return True
        except Exception as exc:
            logger.error(
                "Firestore connectivity verification failed (%s).", type(exc).__name__
            )
            return False

    def close(self) -> None:
        """Release only the Firebase application *this* connector created.

        Safe to call repeatedly and after a failed/aborted connect. Applications
        created elsewhere are never deleted.
        """
        sdk = self._sdk
        owned_app = self._owned_app
        if sdk is not None and owned_app is not None:
            apps = getattr(sdk, "_apps", None)
            name = getattr(owned_app, "name", None)
            if apps is not None and name in apps:
                try:
                    sdk.delete_app(apps[name])
                    logger.info("Firebase connection closed.")
                except Exception as exc:
                    logger.error(
                        "Failed to release the Firebase application owned by this "
                        "connector (%s).",
                        type(exc).__name__,
                    )
        self._sdk = None
        self._owned_app = None
        self.db = None
        self._initialized = False


class MemgraphConnector:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MemgraphConnector, cls).__new__(cls)
            cls._instance._reset_state()
        return cls._instance

    def __init__(self, settings: MemgraphDB):
        # FAST INIT: Store settings, but do NOT connect yet.
        self.setting = settings

    def _reset_state(self) -> None:
        self.driver = None
        self._initialized = False

    @property
    def is_ready(self) -> bool:
        return self._initialized and self.driver is not None

    async def connect(self):
        if self._initialized and self.driver is not None:
            return

        self.driver = GraphDatabase.driver(
            self.setting.memgraph_uri,
            auth=(self.setting.MEMGRAPH_USER, self.setting.MEMGRAPH_PASSWORD),
        )

        retries = 10  # INCREASED FROM 5
        while retries > 0:
            try:
                self.driver.verify_connectivity()
                self._initialized = True
                logger.info("Successfully connected to Memgraph.")
                break
            except Exception as exc:
                # If it's an Auth error, we should fail immediately, not retry.
                message = str(exc).lower()
                if "unauthorized" in message or "auth" in message:
                    # Sanitized: the raw auth error may echo credentials.
                    logger.critical("Memgraph authentication failed.")
                    raise

                retries -= 1
                logger.warning(
                    "Memgraph not ready at %s. Retrying... (%s left)",
                    self.setting.MEMGRAPH_HOST,
                    retries,
                )
                if retries == 0:
                    logger.error(
                        "Failed to connect to Memgraph after bounded retries."
                    )
                    raise
                await asyncio.sleep(5)  # INCREASED FROM 3

    def close(self):
        driver = self.driver
        # Reset state first so a repeated close is a no-op and a later connect
        # starts from a clean slate.
        self.driver = None
        self._initialized = False
        if driver is not None:
            driver.close()
            logger.info("Memgraph connection closed.")


# ---------------------------------------------------------
# STARTUP / SHUTDOWN LIFECYCLE (injectable, testable)
# ---------------------------------------------------------
def _startup_error(stage: str, exc: "Exception | None") -> RuntimeError:
    """Sanitized startup failure: never carries provider/credential text."""
    detail = type(exc).__name__ if exc is not None else "connectivity check failed"
    return RuntimeError(f"{stage} startup failed ({detail}); refusing to start.")


def _safe_close(connector) -> None:
    try:
        connector.close()
    except Exception as exc:
        logger.error(
            "Failed to clean up %s (%s).", type(connector).__name__, type(exc).__name__
        )


async def startup_databases(memgraph, firestore, *, enabled: "bool | None" = None) -> None:
    """Bring up the required graph DB and the optional Firestore dependency.

    - Graph-only by default; Firestore is connected and verified only when
      explicitly enabled (``enabled`` or ``FIRESTORE_ENABLED``).
    - Invalid config raises before anything is initialized.
    - Any failure closes whatever was already initialized and re-raises a
      sanitized error, so startup never continues in a degraded state.
    """
    if enabled is None:
        enabled = firestore_enabled()

    if enabled:
        try:
            firestore.connect(enabled=True)
        except Exception as exc:
            _safe_close(firestore)
            _safe_close(memgraph)
            raise _startup_error("Firestore", exc) from None
        if not firestore.verify_connectivity():
            _safe_close(firestore)
            _safe_close(memgraph)
            raise _startup_error("Firestore", None) from None

    try:
        await memgraph.connect()
    except Exception as exc:
        _safe_close(firestore)
        _safe_close(memgraph)
        raise _startup_error("Memgraph", exc) from None


async def shutdown_databases(memgraph, firestore) -> None:
    """Close both dependencies; Firestore is closed even if the graph fails."""
    try:
        memgraph.close()
    finally:
        firestore.close()


def dependency_health(memgraph, firestore) -> dict:
    """Honest, side-effect-free dependency status for the health endpoint.

    A disabled Firestore is reported as ``disabled`` and never as online, so the
    root endpoint cannot imply a Firebase connection that does not exist.
    """
    try:
        enabled = firestore_enabled()
    except ValueError:
        firestore_state = {
            "enabled": None,
            "ready": False,
            "status": "invalid_configuration",
        }
    else:
        ready = bool(getattr(firestore, "is_ready", False))
        if not enabled:
            firestore_state = {"enabled": False, "ready": False, "status": "disabled"}
        else:
            firestore_state = {
                "enabled": True,
                "ready": ready,
                "status": "ready" if ready else "not_ready",
            }

    return {
        "memgraph": {
            "required": True,
            "ready": bool(getattr(memgraph, "is_ready", False)),
        },
        "firestore": {"required": False, **firestore_state},
    }


# ---------------------------------------------------------
# MODULE EXPORTS (These are now instant and 100% safe to import anywhere)
# ---------------------------------------------------------
firestore_db = FireStoreConnector()
memgraph_db = MemgraphConnector(db_settings)

def get_memgraph_connector() -> MemgraphConnector:
    return memgraph_db

def get_firestore_connector() -> FireStoreConnector:
    return firestore_db
