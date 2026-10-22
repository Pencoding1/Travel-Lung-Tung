# Agent workflow for this workspace

- Codex owns planning, test cases, independent QA and acceptance. Read docs/project/FOUR_PHASE_PLAN.md and docs/project/EXECUTOR_POLICY.md before delegated work. Follow the scoped brief and one-writer ownership.
- Never enumerate environment variables or read raw secret-bearing config, .env, credentials, auth files or unrelated session history to discover a key or session ID. Parent captures session IDs from CLI output; unknown is acceptable.
- For a legitimate credential check, use the reviewed scripts/agent_guardrails/safe_secret_probe.py interface for only the requested variable presence/type/length. Until the helper passes QA, leave sensitive checks pending. Never print values, prefixes, suffixes or value hashes.
- Guard QA and default-home registration are proven in docs/project/handoffs/HM-055/parent-registration-proof.json. For a terminal invocation under the installed Hermes hook, use the fully absolute sibling helper path C:/Users/duyan/AppData/Local/hermes/agent-hooks/secret_guardrails/safe_secret_probe.py, with only reviewed --env/--file/--format/--name arguments. Relative helper paths are intentionally blocked. This does not certify old gateways or other profiles.
- Do not read or attach KEY_EXPOSURE_EXCERPT_PRIVATE.txt to prompts, reports or bundles. It is a private user-requested incident excerpt; the user confirmed the exposed token retired.
- Do not rephrase, encode, rename commands or switch tools to perform a denied action. Stop and return a sanitized reason. Preserve existing approval/domain guards; no bypass flags.
- Executive artifacts: E:/Agent_Artifact/TVLT_2026/YYYY-MM-DD/<agent-name>/. Use reviewed local domain lists, never ALL or wildcards, never edit global allowlists.
- Preserve frozen primary data and unrelated user changes. Distinguish synthetic tests, actual engine evidence and scientific experiments.
