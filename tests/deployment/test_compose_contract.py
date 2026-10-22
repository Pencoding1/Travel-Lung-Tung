"""Structural deployment contract tests for the local Compose definition.

These tests never start services, never pull/build images and never load a real
``.env``. They exercise only:

* ``docker compose --env-file .env.example config --no-env-resolution`` with
  ``--quiet`` / ``--services`` / ``--profiles`` (full rendered config is never
  requested), and
* textual/structural assertions over the tracked Compose and metadata files.

``--env-file`` alone does **not** stop Compose from resolving each service's
``env_file``; ``--no-env-resolution`` is required so that only the template is
read. Every configuration command and doc in this repo must carry that flag.

When the Docker CLI is unavailable the engine-backed checks are skipped rather
than failing, so the static contract still runs in a sandbox.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yaml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
INTEGRATION_COMPOSE = REPO_ROOT / "docker-compose.integration.yaml"
INTEGRATION_ENV_EXAMPLE = REPO_ROOT / "docs" / "deployment" / "integration.env.example"

DEFAULT_SERVICES = {
    "memgraph",
    "lab",
    "graphhopper",
    "poi_api",
    "poi_mcp",
    "ai_service",
}
TUNNEL_SERVICE = "ngrok"

# Long, high-entropy assignment values are treated as "looks like a secret".
_SECRETISH = re.compile(r"^[A-Za-z0-9_\-]{20,}$")


@pytest.fixture(scope="module")
def compose_text() -> str:
    return COMPOSE.read_text(encoding="utf-8")


def _service_block(text: str, name: str) -> str:
    """Return the indented YAML block for one top-level service."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.rstrip() == f"  {name}:":
            start = i
            break
    assert start is not None, f"service {name!r} not present in docker-compose.yaml"
    block = [lines[start]]
    for line in lines[start + 1:]:
        if line.strip() and not line.startswith("  ") and not line.startswith(" " * 4):
            # A new top-level key (e.g. `volumes:`) ends the service block.
            break
        if re.match(r"^  \S", line):
            # A sibling service starts with exactly two spaces of indentation.
            break
        block.append(line)
    return "\n".join(block)


SAFE_CONFIG_FLAGS = ("--no-env-resolution",)


def _config_command(
    *extra: str,
    profile: str | None = None,
    compose: Path = COMPOSE,
    env_file: Path = ENV_EXAMPLE,
) -> list[str]:
    """Build a safe, read-only `docker compose config` argument vector.

    The vector only ever selects the template with ``--env-file`` and asks for
    ``--no-env-resolution`` plus a bounded summary flag; the full rendered
    configuration is never requested.
    """
    cmd = ["docker", "compose", "-f", str(compose), "--env-file", str(env_file)]
    if profile:
        cmd += ["--profile", profile]
    cmd += ["config", *SAFE_CONFIG_FLAGS, *extra]
    return cmd


def _docker_compose_config(
    *extra: str,
    profile: str | None = None,
    compose: Path = COMPOSE,
    env_file: Path = ENV_EXAMPLE,
):
    """Run a client-side compose config query. Returns stdout or None if skipped."""
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not available")
    cmd = _config_command(*extra, profile=profile, compose=compose, env_file=env_file)
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
    )
    if proc.returncode != 0:
        # Keep failure output sanitized and short; config errors never echo
        # interpolated secret values, but truncate regardless.
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        pytest.fail(
            "docker compose config failed: " + " | ".join(detail[-3:])[:400]
        )
    return proc.stdout


def test_config_commands_are_safe() -> None:
    """Prove the argument vector only reads the template and never renders it."""
    for extra in (["--quiet"], ["--services"], ["--profiles"], ["--images"]):
        cmd = _config_command(*extra)
        assert "--no-env-resolution" in cmd
        assert "--env-file" in cmd
        assert str(ENV_EXAMPLE) in cmd
        assert cmd[cmd.index("config") + 1] == "--no-env-resolution"
        assert cmd.count("config") == 1
    assert "--no-env-resolution" in _config_command("--services", profile="tunnel")


def test_jwt_wiring_is_explicit_and_consistent(compose_text: str) -> None:
    for name in ("poi_api", "poi_mcp"):
        block = _service_block(compose_text, name)
        assert "JWT_SECRET=${JWT_SECRET:?" in block, name
        assert "JWT_ALGORITHM=${JWT_ALGORITHM:-HS256}" in block, name
    # The `:?` form fails closed instead of injecting an empty secret.
    assert "JWT_SECRET=${JWT_SECRET}" not in compose_text


def test_no_literal_ngrok_token(compose_text: str) -> None:
    matches = re.findall(r"NGROK_AUTHTOKEN=(\S+)", compose_text)
    assert matches, "docker-compose.yaml must reference NGROK_AUTHTOKEN"
    for value in matches:
        assert value == "${NGROK_AUTHTOKEN}", (
            "NGROK_AUTHTOKEN must be sourced from the environment, never a "
            "literal credential"
        )


def test_tunnel_is_opt_in_profile(compose_text: str) -> None:
    ngrok = _service_block(compose_text, TUNNEL_SERVICE)
    assert 'profiles: ["tunnel"]' in ngrok
    assert "--url=${NGROK_DOMAIN}" in ngrok


def test_ai_service_mcp_and_model_wiring(compose_text: str) -> None:
    ai = _service_block(compose_text, "ai_service")
    assert "MCP_SERVER_URL=${MCP_SERVER_URL:-http://poi_mcp:8001/sse}" in ai
    assert "GEMINI_MODEL=${GEMINI_MODEL:-gemini-2.5-pro}" in ai
    assert "GEMINI_API_KEY=${GEMINI_API_KEY}" in ai
    assert "OLLAMA_HOST" not in ai, "Ollama is unused by ai_service"


def test_published_ports_are_loopback_only(compose_text: str) -> None:
    for line in compose_text.splitlines():
        m = re.match(r'^\s*-\s*"(\d+:\d+)"\s*$', line)
        assert m is None, f"port must bind 127.0.0.1: {line.strip()}"


def test_storage_volumes_preserved(compose_text: str) -> None:
    assert "mg_lib:/var/lib/memgraph" in compose_text
    assert "mg_log:/var/log/memgraph" in compose_text
    for named in ("mg_lib:", "mg_log:", "mg_etc:"):
        assert re.search(rf"^  {re.escape(named)}$", compose_text, re.M), named


def test_poi_env_file_reference_preserved(compose_text: str) -> None:
    assert compose_text.count("path: ./POI_service/.env") == 2


def test_pulled_images_are_variable_with_defaults(compose_text: str) -> None:
    for var in ("MEMGRAPH_IMAGE", "MEMGRAPH_LAB_IMAGE", "NGROK_IMAGE"):
        assert f"${{{var}:-" in compose_text, var
    assert "GRAPHHOPPER_BASE_IMAGE: ${GRAPHHOPPER_BASE_IMAGE:-" in compose_text


def test_referenced_package_paths_exist() -> None:
    assert (REPO_ROOT / "shared_lib" / "pyproject.toml").is_file()
    assert (REPO_ROOT / "ai_service" / "domains").is_dir()
    assert (REPO_ROOT / "POI_service" / "app").is_dir()
    assert (REPO_ROOT / "backend_service" / "app").is_dir()
    assert (REPO_ROOT / "crawler_service" / "app" / "main.py").is_file()

    ai_pyproject = (REPO_ROOT / "ai_service" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert 'packages = ["domains"]' in ai_pyproject
    assert 'packages = ["app"]' not in ai_pyproject

    ai_dockerfile = (REPO_ROOT / "ai_service" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    assert "COPY shared_lib/ ./shared_lib/" in ai_dockerfile
    assert "uv pip install -e ./shared_lib -e ./ai_service" in ai_dockerfile


def test_env_example_uses_placeholders_only() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    required = {
        "MEMGRAPH_USER",
        "MEMGRAPH_PASSWORD",
        "JWT_SECRET",
        "FIRESTORE_ENABLED",
        "MEMORY_DB_PATH",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "MCP_SERVER_URL",
        "NGROK_AUTHTOKEN",
        "NGROK_DOMAIN",
    }
    for key in required:
        assert re.search(rf"^#?\s*{key}=", text, re.M), key
    # The tunnel stays disabled by default: its keys are commented out.
    assert re.search(r"^# NGROK_AUTHTOKEN=", text, re.M)
    # Durable memory stays off by default: its path is an empty assignment.
    assert re.search(r"^MEMORY_DB_PATH=\s*$", text, re.M)
    # Each non-commented assignment is either a placeholder or a documented
    # non-secret literal (host/algorithm/model/url/port/flag).
    allowed_non_placeholder = {
        "MEMGRAPH_HOST",
        "MEMGRAPH_PORT",
        "JWT_ALGORITHM",
        "FIRESTORE_ENABLED",
        "GEMINI_MODEL",
        "MCP_SERVER_URL",
    }
    for line in text.splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.+)$", line)
        if not m:
            continue
        key, value = m.groups()
        if key in allowed_non_placeholder:
            continue
        assert value.startswith("replace_me"), f"{key} must be a placeholder"


def test_no_secret_literal_in_deployment_artifacts() -> None:
    targets = [COMPOSE, ENV_EXAMPLE, Path(__file__).resolve()]
    targets += [p for p in (REPO_ROOT / "docs" / "deployment").glob("**/*")]
    targets += [p for p in (REPO_ROOT / "tests" / "deployment").glob("**/*.py")]
    for path in targets:
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for value in re.findall(r"NGROK_AUTHTOKEN=(\S+)", content):
            assert not _SECRETISH.match(value), (
                f"looks like a literal NGROK_AUTHTOKEN in {path.name}"
            )


def test_default_services_exclude_tunnel() -> None:
    out = _docker_compose_config("--services")
    services = set(out.split())
    assert services == DEFAULT_SERVICES
    assert TUNNEL_SERVICE not in services


def test_tunnel_profile_is_declared_and_adds_ngrok() -> None:
    profiles = _docker_compose_config("--profiles").split()
    assert "tunnel" in profiles
    with_tunnel = set(
        _docker_compose_config("--services", profile="tunnel").split()
    )
    assert TUNNEL_SERVICE in with_tunnel


def test_compose_config_quiet_succeeds() -> None:
    _docker_compose_config("--quiet")


def test_runbook_config_commands_are_safe() -> None:
    runbook = REPO_ROOT / "docs" / "deployment" / "RUNBOOK.md"
    if not runbook.is_file():
        pytest.skip("runbook not present")
    for line in runbook.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("docker compose") and " config" in stripped:
            assert "--no-env-resolution" in stripped, stripped


# ---------------------------------------------------------------------------
# Main-stack optional-dependency wiring (Firebase / memory / shared auth key)
# ---------------------------------------------------------------------------


def test_firestore_flag_is_explicit_and_defaults_off(compose_text: str) -> None:
    for name in ("poi_api", "poi_mcp"):
        block = _service_block(compose_text, name)
        assert "FIRESTORE_ENABLED=${FIRESTORE_ENABLED:-false}" in block, name


def test_ai_service_requires_shared_hs256_key(compose_text: str) -> None:
    ai = _service_block(compose_text, "ai_service")
    assert "JWT_SECRET=${JWT_SECRET:?JWT_SECRET is required}" in ai
    assert "JWT_ALGORITHM=${JWT_ALGORITHM:-HS256}" in ai
    # The `:?` form fails closed instead of injecting an empty secret.
    assert "JWT_SECRET=${JWT_SECRET}" not in ai


def test_main_durable_memory_is_opt_in_on_named_volume(compose_text: str) -> None:
    ai = _service_block(compose_text, "ai_service")
    # Blank default means durable memory stays OFF.
    assert "MEMORY_DB_PATH=${MEMORY_DB_PATH:-}" in ai
    # Any enabled path lives on a dedicated named volume, never a bind mount.
    assert "ai_memory:/var/lib/ai_memory" in ai
    assert re.search(r"^  ai_memory:\s*$", compose_text, re.M)


# ---------------------------------------------------------------------------
# Isolated integration stack (docker-compose.integration.yaml)
# ---------------------------------------------------------------------------

INTEGRATION_SERVICES = {
    "memgraph",
    "graphhopper",
    "poi_api",
    "poi_mcp",
    "ai_service",
    "backend_service",
}
PRODUCTION_VOLUMES = ("mg_lib", "mg_log", "mg_etc")


@pytest.fixture(scope="module")
def integration_text() -> str:
    return INTEGRATION_COMPOSE.read_text(encoding="utf-8")


def _decomment(text: str) -> str:
    """Drop full-line YAML comments so prose never trips structural checks."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def _section_names(text: str, section: str) -> list[str]:
    """Return the top-level mapping keys directly under a column-0 section."""
    names: list[str] = []
    active = False
    for line in text.splitlines():
        if re.match(rf"^{re.escape(section)}:\s*$", line):
            active = True
            continue
        if active:
            if line and not line.startswith(" "):
                break
            m = re.match(r"^  ([A-Za-z0-9_\-]+):\s*$", line)
            if m:
                names.append(m.group(1))
    return names


def test_integration_uses_a_separate_project(integration_text: str) -> None:
    m = re.search(r"^name:\s*(\S+)\s*$", integration_text, re.M)
    assert m is not None, "integration compose must set a top-level project name"
    assert m.group(1) == "tvlt_integration"


def test_integration_has_no_fixed_container_names(integration_text: str) -> None:
    assert "container_name:" not in _decomment(integration_text)


def test_integration_declares_only_its_own_named_volumes(integration_text: str) -> None:
    body = _decomment(integration_text)
    vols = _section_names(body, "volumes")
    assert vols, "integration compose must declare named volumes"
    assert all(v.startswith("int_") for v in vols), vols
    assert re.search(r"^\s*external:\s*true", body, re.M) is None
    for prod in PRODUCTION_VOLUMES:
        # Match the production name as a whole token, so `int_mg_lib` is fine.
        assert (
            re.search(rf"(?<![A-Za-z0-9_]){re.escape(prod)}(?![A-Za-z0-9_])", body)
            is None
        ), f"integration must not reference {prod}"


def test_integration_avoids_production_bind_mounts(integration_text: str) -> None:
    body = _decomment(integration_text)
    for path in ("./POI_service", "./shared_lib", "./ai_service", "./graphhopper/data:"):
        assert path not in body, f"integration must not reuse bind mount {path}"
    # The only source mounts are immutable GraphHopper inputs, read-only.
    assert (
        "./graphhopper/data/hcmc-latest.osm.pbf:/app_data/hcmc-latest.osm.pbf:ro"
        in body
    )
    assert "./graphhopper/data/config.yml:/app_data/config.yml:ro" in body


def test_integration_ports_are_loopback_and_unique(
    integration_text: str, compose_text: str
) -> None:
    # No bare, non-loopback port mapping remains.
    for line in integration_text.splitlines():
        assert re.match(r'^\s*-\s*"(\d+:\d+)"\s*$', line) is None, line.strip()
    int_ports = [int(p) for p in re.findall(r'"127\.0\.0\.1:(\d+):\d+"', integration_text)]
    assert int_ports, "integration stack must publish loopback ports"
    assert len(int_ports) == len(set(int_ports)), "duplicate integration host ports"
    # A dedicated high range documents that distinct ports, not the project
    # name, are what avoid host-port collisions with the main stack.
    assert all(17000 <= p < 19000 for p in int_ports), int_ports
    main_ports = {
        int(p) for p in re.findall(r'"127\.0\.0\.1:(\d+):\d+"', compose_text)
    }
    assert not (set(int_ports) & main_ports), "host port collision with main stack"


def test_integration_core_services_present(integration_text: str) -> None:
    body = _decomment(integration_text)
    services = set(_section_names(body, "services"))
    assert services == INTEGRATION_SERVICES, services
    assert "ngrok" not in body.lower()
    assert "profiles:" not in body


def test_integration_requires_explicit_secrets(integration_text: str) -> None:
    body = _decomment(integration_text)
    assert (
        "JWT_SECRET=${INTEGRATION_JWT_SECRET:?INTEGRATION_JWT_SECRET is required}"
        in body
    )
    assert (
        "GEMINI_API_KEY=${INTEGRATION_GEMINI_API_KEY:?INTEGRATION_GEMINI_API_KEY is required}"
        in body
    )
    # The integration stack never inherits the production variables or env file.
    assert "JWT_SECRET=${JWT_SECRET" not in body
    assert "GEMINI_API_KEY=${GEMINI_API_KEY" not in body
    assert "POI_service/.env" not in body
    # No literal integration secret assignment may appear in the compose file.
    assert (
        re.search(
            r"INTEGRATION_(?:JWT_SECRET|GEMINI_API_KEY|MEMGRAPH_PASSWORD)=\S",
            body,
        )
        is None
    )


def test_integration_memory_is_off_by_default_on_named_volume(
    integration_text: str,
) -> None:
    ai = _service_block(integration_text, "ai_service")
    assert "MEMORY_DB_PATH=${INTEGRATION_MEMORY_DB_PATH:-}" in ai
    assert "int_ai_memory:/var/lib/ai_memory" in ai
    assert re.search(r"^  int_ai_memory:\s*$", integration_text, re.M)


def test_integration_graphhopper_cache_is_dedicated(integration_text: str) -> None:
    gh = _service_block(integration_text, "graphhopper")
    assert "int_graphcache:/tmp/hcmc-gh" in gh


def test_integration_env_template_is_dummy_only() -> None:
    text = INTEGRATION_ENV_EXAMPLE.read_text(encoding="utf-8")
    for key in (
        "INTEGRATION_JWT_SECRET",
        "INTEGRATION_GEMINI_API_KEY",
        "INTEGRATION_MEMGRAPH_USER",
        "INTEGRATION_MEMGRAPH_PASSWORD",
    ):
        assert re.search(rf"^{key}=", text, re.M), key
    assert re.search(r"^INTEGRATION_MEMORY_DB_PATH=\s*$", text, re.M)
    allowed_literals = {"INTEGRATION_JWT_ALGORITHM", "INTEGRATION_FIRESTORE_ENABLED"}
    for m in re.finditer(r"^([A-Z0-9_]+)=(.+)$", text, re.M):
        key, value = m.groups()
        if key in allowed_literals:
            continue
        assert value.startswith("replace_me"), f"{key} must be a placeholder"


def test_integration_config_commands_are_safe() -> None:
    for extra in (["--quiet"], ["--services"], ["--profiles"], ["--images"]):
        cmd = _config_command(
            *extra, compose=INTEGRATION_COMPOSE, env_file=INTEGRATION_ENV_EXAMPLE
        )
        assert "--no-env-resolution" in cmd
        assert str(INTEGRATION_COMPOSE) in cmd
        assert str(INTEGRATION_ENV_EXAMPLE) in cmd
        assert cmd[cmd.index("config") + 1] == "--no-env-resolution"


def test_integration_config_quiet_succeeds() -> None:
    _docker_compose_config(
        "--quiet", compose=INTEGRATION_COMPOSE, env_file=INTEGRATION_ENV_EXAMPLE
    )


def test_integration_services_are_engine_resolved_without_tunnel() -> None:
    out = _docker_compose_config(
        "--services", compose=INTEGRATION_COMPOSE, env_file=INTEGRATION_ENV_EXAMPLE
    )
    services = set(out.split())
    assert services == INTEGRATION_SERVICES
    assert "ngrok" not in services


# ---------------------------------------------------------------------------
# backend_service packaging + isolated wiring (OC-030)
# ---------------------------------------------------------------------------

BACKEND_DOCKERFILE = REPO_ROOT / "backend_service" / "Dockerfile"


def _dockerfile_body(text: str) -> str:
    """Drop full-line Dockerfile comments so prose never trips structural checks."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def test_backend_dockerfile_runs_documented_app_on_8003() -> None:
    body = _dockerfile_body(BACKEND_DOCKERFILE.read_text(encoding="utf-8"))
    assert "EXPOSE 8003" in body
    cmd = [line for line in body.splitlines() if line.startswith("CMD ")]
    assert len(cmd) == 1, "backend Dockerfile must declare exactly one CMD entrypoint"
    assert "uvicorn" in cmd[0]
    assert "app.main:app" in cmd[0]
    assert "8003" in cmd[0]
    # The dependency source is the locked backend export (build pattern).
    assert "uv export --package backend_service" in body


def test_backend_dockerfile_healthcheck_is_liveness_only() -> None:
    body = _dockerfile_body(BACKEND_DOCKERFILE.read_text(encoding="utf-8"))
    assert "HEALTHCHECK" in body
    assert "127.0.0.1:8003/health" in body
    # Never probe readiness (which depends on durable storage) in the image.
    assert "/ready" not in body


def test_backend_dockerfile_drops_stale_no_entrypoint_disclaimer() -> None:
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8").lower()
    assert "no runnable fastapi application" not in text
    assert "not expected to start" not in text
    assert "has no cmd" not in text


def test_backend_service_is_absent_from_production_stack(compose_text: str) -> None:
    services = set(_section_names(compose_text, "services"))
    assert "backend_service" not in services
    assert DEFAULT_SERVICES <= services


def test_integration_backend_service_is_isolated_and_durable(
    integration_text: str,
) -> None:
    body = _decomment(integration_text)
    block = _service_block(integration_text, "backend_service")
    # Dedicated loopback host port mapped to the documented container port.
    assert '"127.0.0.1:18003:8003"' in block
    # Its own durable named volume with the SQLite file inside it.
    assert "int_backend_drafts:/var/lib/backend_drafts" in block
    assert "ITINERARY_STORAGE=sqlite" in block
    assert "ITINERARY_SQLITE_PATH=/var/lib/backend_drafts/drafts.sqlite3" in block
    # No anonymous (none) or Firebase-backed default, and not interpolated.
    assert "ITINERARY_STORAGE=none" not in block
    assert "ITINERARY_STORAGE=firebase" not in block
    assert "ITINERARY_STORAGE=${" not in block
    # Same shared, explicitly-required HS256 contract as the rest of the stack.
    assert (
        "JWT_SECRET=${INTEGRATION_JWT_SECRET:?INTEGRATION_JWT_SECRET is required}"
        in block
    )
    assert "JWT_ALGORITHM=${INTEGRATION_JWT_ALGORITHM:-HS256}" in block
    # Separate from the optional AI durable-memory profile: no silent chat save.
    assert "int_ai_memory" not in block
    assert "MEMORY_DB_PATH" not in block
    # No historical/production volume mount and no fixed container name.
    for prod in PRODUCTION_VOLUMES:
        assert (
            re.search(rf"(?<![A-Za-z0-9_]){re.escape(prod)}(?![A-Za-z0-9_])", block)
            is None
        ), f"backend_service must not reference {prod}"
    assert "container_name:" not in body
    # The stack owns a dedicated, int_-prefixed named volume for drafts.
    assert re.search(r"^  int_backend_drafts:\s*$", integration_text, re.M)
    assert "int_backend_drafts:/var/lib/backend_drafts" in body


def test_integration_backend_port_is_unique_and_loopback(integration_text: str) -> None:
    block = _service_block(integration_text, "backend_service")
    ports = re.findall(r'"127\.0\.0\.1:(\d+):(\d+)"', block)
    assert ports == [("18003", "8003")]


def test_runbook_documents_backend_workflow_with_placeholders() -> None:
    runbook = (REPO_ROOT / "docs" / "deployment" / "RUNBOOK.md").read_text(
        encoding="utf-8"
    )
    for token in (
        "backend_service",
        "18003",
        "app.main:app",
        "ITINERARY_STORAGE=sqlite",
        "/api/v1/itineraries",
        "Authorization: Bearer",
    ):
        assert token in runbook, token
    # The expected integration service list must name the backend.
    assert "`backend_service`" in runbook


def test_deployment_docs_embed_no_credentials() -> None:
    secret_vars = (
        "JWT_SECRET",
        "INTEGRATION_JWT_SECRET",
        "GEMINI_API_KEY",
        "INTEGRATION_GEMINI_API_KEY",
        "INTEGRATION_MEMGRAPH_PASSWORD",
    )
    paths = list((REPO_ROOT / "docs" / "deployment").glob("**/*"))
    paths.append(INTEGRATION_COMPOSE)
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for var in secret_vars:
            for match in re.finditer(rf"{re.escape(var)}=(\S+)", text):
                value = match.group(1).strip('"').strip("'")
                if value.startswith("replace_me"):
                    continue
                assert not _SECRETISH.match(value), (
                    f"secret-looking {var} in {path.name}"
                )
