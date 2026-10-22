"""Bootstrap the *actual* POI domain model, isolated from other app namespaces.

The POI model lives under ``POI_service/app`` and imports as the top-level
``app`` package. Adding that root to ``sys.path`` must never shadow or collide
with ``crawler_service.app`` (which imports as ``crawler_service.app``). This
loader:

* refuses to reuse an already-imported ``app`` that is not POI_service's;
* imports the real model once, under its real module name;
* returns the real ``POI`` class so callers validate with the production schema
  rather than a hand-copied parallel schema.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from crawler_service.app.acquisition.resolution import ConfigError

_REPO_ROOT = Path(__file__).resolve().parents[3]
_POI_SERVICE_ROOT = _REPO_ROOT / "POI_service"
_POI_MODULE = "app.core.domain.graph_entities"


def _poi_service_on_path() -> None:
    if _POI_SERVICE_ROOT.is_dir() and str(_POI_SERVICE_ROOT) not in sys.path:
        sys.path.insert(0, str(_POI_SERVICE_ROOT))


def load_poi_model() -> Any:
    """Return the production ``POI`` model class, or raise ``ConfigError``."""

    existing_module = sys.modules.get(_POI_MODULE)
    if existing_module is not None and hasattr(existing_module, "POI"):
        return existing_module.POI

    loaded_app = sys.modules.get("app")
    if loaded_app is not None:
        loaded_path = (getattr(loaded_app, "__file__", "") or "").replace("\\", "/")
        if "POI_service" not in loaded_path:
            raise ConfigError(
                "a foreign top-level 'app' package is already imported "
                f"({loaded_path or loaded_app!r}); the POI model cannot be loaded "
                "in isolation (run this capability in a clean interpreter)"
            )

    _poi_service_on_path()
    try:
        module = importlib.import_module(_POI_MODULE)
    except Exception as exc:  # pragma: no cover - environment dependent
        raise ConfigError(
            f"cannot import the POI domain model from {_POI_SERVICE_ROOT}: {exc}"
        ) from exc
    if not hasattr(module, "POI"):
        raise ConfigError(f"{_POI_MODULE} does not expose a POI model")
    return module.POI
