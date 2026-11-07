# Compose v1.1 live acceptance — 28/10/2026

Authority: user requests actual pipeline and explicitly permits Docker Compose loading POI_service/.env + root .env through --env-file. Never display resolved config/env values or inspect raw secrets. No tunnel/public deployment, no primary mutation, no old cohort overwrite.

1. Inspect names/state/ports, known public Compose/Dockerfiles and safe metadata only. Already observed no TVLT containers or service ports; process/root JWT missing but service-file JWT present.
2. Exclude secret-bearing paths and legacy from build context. This packaging-only correction is needed before build; no business behavior changes.
3. Attempt actual Compose startup/build of memgraph/graphhopper/poi_api/poi_mcp/ai_service with standard secret loader; omit lab/tunnel. Keep exact observed dependency/provider configuration, do not claim model ready from health.
4. Freeze a new run manifest for 24 v1.1 cases, no unit/mock/ASGI overrides. Validate dependencies/identity/data before positive tests. Missing legitimate authenticated context or prerequisites => BLOCKED, never issue destructive/user-data writes.
5. Actual request responses evaluated against new behavior; absent pipeline/intent fields => FAIL/NOT_VERIFIED as appropriate, external failure distinct. Stop dependent provider branch on auth/permission/rate-limit failure, no fallback or best-of retries.
6. Persist commands/observations/limits in new artifacts. Preserve existing reports and legacy. If stack cannot start, retain exact build/start failure; no fake full-pipeline pass.

Reviewed domains for this task: registry-1.docker.io, auth.docker.io, production.cloudflare.docker.com (Compose image acquisition); ghcr.io (uv image used by checked-in Dockerfiles); pypi.org, files.pythonhosted.org (locked Python packages); deb.debian.org, security.debian.org (official base package repositories if checked-in builds request them); localhost pipeline 127.0.0.1. Application model domains remain only api.typesafe.ai/opencode.ai if actual selected provider is used. No global allowlist changes. Download permissions are limited to these container images/packages for this requested local stack; not arbitrary executable downloads or installation outside task Docker images.
