"""Controlled fakes/fixtures for the OC-040 provider adapter tests.

The fake runner mirrors the real bounded runner contract (argument array, child
environment, bounded output) but never launches a process. Event streams and
session exports mirror the accepted collector shape. Evidence here is mocked
contract evidence only.
"""

from __future__ import annotations

import copy
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from domains.providers.process import CommandResult

PROVIDER = "aibox"
MODEL = "ds/deepseek-flash"
REQUESTED = "aibox/ds/deepseek-flash"
ROUTER_MARKER = "intent classification router"
SYNTHESIS_MARKER = "itinerary selection engine"
TOOL_PROTOCOL = "SERVER TOOL PROTOCOL"
TOOL_RESULT = "[TOOL RESULT"

DEFAULT_TOKENS = {"input": 10, "output": 2, "reasoning": 3,
                  "cache": {"read": 1, "write": 0}, "total": 16}

# Verbatim `opencode run --help` FLAGS/GLOBAL FLAGS section observed from the
# installed CLI v2.0.32 on 2026-10-18: no `--pure` flag is advertised.
HELP_RUN_NO_PURE = """DESCRIPTION
  Run OpenCode with a message

USAGE
  opencode run [flags] [<message...>]

ARGUMENTS
  message... string    Message to send (optional)

FLAGS
  --standalone            Run with a private server instead of the background service
  --server string         Connect to a server URL instead of the background service
  --continue, -c          Continue the last session
  --session, -s string    Session ID to continue, or to create if it does not exist
  --fork                  Fork the session before continuing
  --model, -m string      Model to use in the format provider/model#variant
  --agent string          Agent to use
  --format choice         Output format (choices: default, json)
  --file, -f string       File to attach to the message
  --title string          Session title
  --thinking              Show thinking blocks
  --auto                  Auto-approve permissions that are not explicitly denied

GLOBAL FLAGS
  --help, -h                                                          Show help information
  --version, -v                                                       Show version information
"""

# Hypothetical older help text that does advertise the flag.
HELP_RUN_WITH_PURE = HELP_RUN_NO_PURE.replace(
    "  --auto                  Auto-approve permissions that are not explicitly denied",
    "  --pure                  Run without external plugins\n"
    "  --auto                  Auto-approve permissions that are not explicitly denied")

CLI_VERSION_TEXT = "opencode v2.0.32"

# Verbatim shape of `opencode session export --help` (v2.0.32): the read-only
# route is a `session` subcommand and exposes --standalone/--server/--sanitize.
HELP_EXPORT_STANDALONE = """DESCRIPTION
  Export session data as JSON

USAGE
  opencode session export [flags] [<session>]

FLAGS
  --standalone       Run with a private server instead of the background service
  --server string    Connect to a server URL instead of the background service
  --sanitize         Redact conversation text before export

GLOBAL FLAGS
  --help, -h    Show help information
"""

HELP_EXPORT_NO_STANDALONE = HELP_EXPORT_STANDALONE.replace(
    "  --standalone       Run with a private server instead of the background service\n",
    "")

HELP_RUN_NO_SERVER = HELP_RUN_NO_PURE.replace(
    "  --server string         Connect to a server URL instead of the background service\n",
    "")

HELP_EXPORT_NO_SERVER = HELP_EXPORT_STANDALONE.replace(
    "  --server string    Connect to a server URL instead of the background service\n",
    "")


class FakeHelpRunner:
    """Answers ``--version`` / ``run --help`` / ``session export --help``."""

    def __init__(self, help_text=HELP_RUN_NO_PURE, version_text=CLI_VERSION_TEXT,
                 help_exit=0, fail=False,
                 export_help_text=HELP_EXPORT_STANDALONE, export_help_exit=0):
        self.help_text = help_text
        self.export_help_text = export_help_text
        self.version_text = version_text
        self.help_exit = help_exit
        self.export_help_exit = export_help_exit
        self.fail = fail
        self.calls = []

    def __call__(self, argv, *, cwd, timeout, env, max_output_bytes,
                 cancel_event=None):
        argv = [str(part) for part in argv]
        self.calls.append(list(argv))
        if self.fail:
            raise OSError("synthetic probe failure")
        if "--version" in argv:
            return CommandResult(argv=argv, exit_code=0, duration_seconds=0.01,
                                 timed_out=False, output_overflow=False,
                                 stdout=(self.version_text + "\n").encode(), stderr=b"")
        if "export" in argv:
            return CommandResult(argv=argv, exit_code=self.export_help_exit,
                                 duration_seconds=0.01, timed_out=False,
                                 output_overflow=False,
                                 stdout=self.export_help_text.encode(), stderr=b"")
        return CommandResult(argv=argv, exit_code=self.help_exit,
                             duration_seconds=0.01, timed_out=False,
                             output_overflow=False,
                             stdout=self.help_text.encode(), stderr=b"")

    @property
    def help_probes(self):
        return [call for call in self.calls if "--help" in call]

    @property
    def export_help_probes(self):
        return [call for call in self.help_probes if "export" in call]

    @property
    def version_probes(self):
        return [call for call in self.calls if "--version" in call]


def token_components(tokens=None):
    tokens = tokens or DEFAULT_TOKENS
    cache = tokens.get("cache") or {}
    return {
        "input": tokens.get("input"),
        "output": tokens.get("output"),
        "reasoning": tokens.get("reasoning"),
        "cache_read": cache.get("read"),
        "cache_write": cache.get("write"),
        "total": tokens.get("total"),
    }


def event_text(text, session, message, tokens=None, *,
               reason="stop", tool_use=False, error=False,
               model_hint=None, part_suffix=None, extra_events=None):
    tokens = tokens or DEFAULT_TOKENS
    suffix = part_suffix or session[-4:]
    start = f"prt_{suffix}_start"
    text_id = f"prt_{suffix}_text"
    finish = f"prt_{suffix}_finish"
    events = [{
        "type": "step_start", "timestamp": 1, "sessionID": session,
        "part": {"id": start, "messageID": message, "sessionID": session,
                 "type": "step-start"},
    }]
    if tool_use:
        events.append({
            "type": "tool_use", "timestamp": 2, "sessionID": session,
            "part": {"type": "tool", "tool": "bash", "id": f"prt_{suffix}_tool",
                     "messageID": message, "sessionID": session},
        })
    if error:
        events.append({
            "type": "error", "timestamp": 2, "sessionID": session,
            "error": {"message": "synthetic provider error"},
        })
    text_part = {"id": text_id, "messageID": message, "sessionID": session,
                 "type": "text", "text": text}
    if model_hint:
        text_part["modelID"] = model_hint
    events.append({"type": "text", "timestamp": 3, "sessionID": session,
                   "part": text_part})
    finish_part = {"id": finish, "reason": reason, "messageID": message,
                   "sessionID": session, "type": "step-finish",
                   "tokens": tokens, "cost": 0}
    events.append({"type": "step_finish", "timestamp": 4, "sessionID": session,
                   "part": finish_part})
    if extra_events:
        events.extend(extra_events)
    return "\n".join(json.dumps(event) for event in events)


def export_payload(text, session, message, tokens=None, *,
                   model=MODEL, provider=PROVIDER, finish="stop",
                   role="assistant", include_tokens=True,
                   agent="oc040-test-agent"):
    tokens = tokens or DEFAULT_TOKENS
    suffix = session[-4:]
    parts = [
        {"type": "step-start", "id": f"prt_{suffix}_start",
         "messageID": message, "sessionID": session},
        {"type": "text", "text": text, "id": f"prt_{suffix}_text",
         "messageID": message, "sessionID": session},
        {"type": "step-finish", "reason": finish or "stop", "tokens": tokens,
         "id": f"prt_{suffix}_finish", "messageID": message,
         "sessionID": session},
    ]
    info = {"role": role, "id": message, "sessionID": session,
            "finish": finish}
    if include_tokens:
        info["tokens"] = tokens
    if role == "assistant":
        info["modelID"] = model
        info["providerID"] = provider
    if agent is not None:
        info["agent"] = agent
    return {
        "info": {"id": session, "version": "1.18.35",
                 "agent": agent,
                 "model": {"id": model, "providerID": provider}},
        "messages": [
            {"info": {"role": "user", "id": "msg_user", "sessionID": session},
             "parts": [{"type": "text", "text": "prompt",
                        "id": "prt_user", "messageID": "msg_user",
                        "sessionID": session}]},
            {"info": info, "parts": parts},
        ],
    }


def call_fixture(text, session="ses_test0001", message="msg_test0001",
                 tokens=None, *, export_kwargs=None, **event_kwargs):
    return (event_text(text, session, message, tokens, **event_kwargs).encode(),
            json.dumps(export_payload(text, session, message, tokens,
                                      **(export_kwargs or {}))).encode())


_AGENT_PLACEHOLDERS = frozenset({
    "oc040-test-agent", "oc040-transport", "t051-test-agent",
})


def _prompt_from_argv(argv):
    """Read the test-only prompt from either the argv path or --file."""
    if "--file" in argv:
        index = argv.index("--file")
        try:
            return Path(argv[index + 1]).read_text(encoding="utf-8")
        except (OSError, IndexError, UnicodeDecodeError):
            return ""
    return argv[-1]


def _record_prompt_input(argv, record):
    """Record the prompt and exact file bytes for focused input tests."""
    if "--file" in argv:
        index = argv.index("--file")
        try:
            raw = Path(argv[index + 1]).read_bytes()
        except (OSError, IndexError):
            raw = b""
        record["prompt_file_bytes"] = raw
        record["prompt_file_name"] = Path(argv[index + 1]).name
        record["prompt_file_path"] = argv[index + 1]
        record["prompt"] = raw.decode("utf-8", "replace")
    else:
        record["prompt"] = argv[-1]


def _rebind_export_agent(raw, cwd):
    """Point a placeholder export agent at the per-call agent we launched.

    Missing/foreign agent fixtures are left untouched so the adapter's
    fail-closed tests still observe them.
    """
    if not raw:
        return raw
    try:
        document = json.loads(raw.decode("utf-8"))
    except (AttributeError, ValueError, UnicodeDecodeError):
        return raw
    try:
        config = json.loads((Path(cwd) / "opencode.json").read_text(
            encoding="utf-8"))
        actual = config.get("default_agent")
    except (OSError, ValueError):
        return raw
    if not isinstance(actual, str) or not actual:
        return raw

    def rebind(node):
        if isinstance(node, dict) and node.get("agent") in _AGENT_PLACEHOLDERS:
            node["agent"] = actual

    rebind(document.get("info"))
    for message in document.get("messages") or []:
        rebind(message)
        if isinstance(message, dict):
            rebind(message.get("info"))
    return json.dumps(document).encode()


# ---------------------------------------------------------------------------
# V2 (installed v2.0.32) stream/export shapes
# ---------------------------------------------------------------------------
def event_text_v2(text, session="ses_v2test01", message="msg_v2test01",
                  *, tool_use=False, extra_events=None):
    """One text event, exactly as the installed CLI emits it (no step_finish)."""
    suffix = session[-4:]
    events = []
    if tool_use:
        events.append({
            "type": "tool_use", "timestamp": 2, "sessionID": session,
            "part": {"partID": f"prt_{suffix}_tool", "sessionID": session,
                     "messageID": message, "type": "tool", "id": "call_qa_1",
                     "tool": "read",
                     "state": {"status": "error",
                               "error": "Tools are disabled after the maximum "
                                        "agent steps"}},
        })
    events.append({
        "type": "text", "timestamp": 3, "sessionID": session,
        "part": {"id": f"prt_{suffix}_text-0", "sessionID": session,
                 "messageID": message, "type": "text", "text": text,
                 "time": {"start": 1, "end": 2}},
    })
    if extra_events:
        events.extend(extra_events)
    return "\n".join(json.dumps(event) for event in events)


def export_payload_v2(text, session="ses_v2test01", message="msg_v2test01",
                      tokens=None, *, agent="oc040-test-agent",
                      model=MODEL, provider=PROVIDER, finish="stop",
                      content=None):
    tokens = tokens or DEFAULT_TOKENS
    blocks = content if content is not None else [{"type": "text", "text": text}]
    return {
        "info": {
            "id": session,
            "projectID": "proj_test",
            "agent": agent,
            "model": {"id": model, "providerID": provider,
                      "variant": "default"},
            "cost": 0,
            "tokens": {"input": tokens.get("input", 0),
                       "output": tokens.get("output", 0)},
            "outcome": "succeeded",
            "title": "synthetic",
            "location": {"directory": "C:\\synthetic"},
        },
        "messages": [
            {"id": "msg_switched", "time": {"created": 1},
             "type": "agent-switched", "agent": agent, "previous": agent},
            {"id": "msg_user", "time": {"created": 2}, "text": "prompt",
             "files": [], "type": "user"},
            {"id": message, "time": {"created": 3, "completed": 4},
             "type": "assistant", "agent": agent,
             "model": {"id": model, "providerID": provider,
                       "variant": "default"},
             "content": blocks, "finish": finish, "rawFinish": finish,
             "cost": 0, "tokens": tokens},
            {"id": "msg_idle", "time": {"created": 5}, "type": "idle",
             "outcome": "succeeded"},
        ],
    }


def v2_fixture(text, session="ses_v2test01", message="msg_v2test01",
               tokens=None, **kwargs):
    return (event_text_v2(text, session, message).encode(),
            json.dumps(export_payload_v2(text, session, message, tokens,
                                        **kwargs)).encode())


MODELS_LISTING = REQUESTED + "\n"
FAKE_SERVER_URL = "http://127.0.0.1:40999"


class FakePrivateServer:
    """Explicit unit-test seam for the owned private server.

    It never launches a process and is *not* engine evidence. A test that uses
    it only proves adapter orchestration; the native QA uses the production
    factory against the installed binary.
    """

    def __init__(self, executable=None, workdir=None, env=None, *,
                 timeout=10.0, proof=None, start_error=None,
                 preflight_error=None, close_facts=None, **kwargs):
        self.executable = executable
        self.workdir = workdir
        self.env = dict(env or {})
        self.timeout = timeout
        self._proof = proof
        self._start_error = start_error
        self._preflight_error = preflight_error
        self._close_facts = close_facts or {
            "stdin_closed": True, "process_terminal": True,
            "port_closed": True}
        self.starts = []
        self.preflights = []
        self.closed = []
        self.url = FAKE_SERVER_URL
        self.port = 40999
        self.pid = 4242
        self.version = "2.0.32-synthetic"
        self.ownership_verified = True

    def start(self, cancel_event=None):
        self.starts.append({"cancel_event": cancel_event})
        if self._start_error is not None:
            raise self._start_error

    def preflight(self, agent_id, workdir, alias, *, cancel_event=None):
        self.preflights.append({"agent_id": agent_id, "workdir": workdir,
                                "alias": alias})
        if self._preflight_error is not None:
            raise self._preflight_error
        if self._proof is not None:
            return dict(self._proof, agent_id=agent_id)
        return {
            "status": "agent_projection_verified",
            "agent_id": agent_id,
            "location_verified": True,
            "mode": "primary",
            "steps": 2,
            "system_matches": True,
            "model_ref_present": True,
            "model_matches": True,
            "wildcard_deny": True,
            "no_allow_after_deny": True,
            "permission_rule_count": 20,
        }

    def client_env(self, base=None):
        env = dict(self.env if base is None else base)
        env["OPENCODE_PASSWORD"] = "synthetic-not-a-secret"
        return env

    def facts(self):
        return {"pid": self.pid, "version": self.version,
                "listener_ownership_verified": self.ownership_verified}

    def close(self):
        self.closed.append(dict(self._close_facts))
        return dict(self._close_facts)


class FakeRunner:
    """A bounded-runner stand-in that records argv/env and serves fixtures.

    Dispatch mirrors the installed V2 routes:
    ``models --standalone`` (readiness), ``session export --standalone <id>``
    (provenance) and ``run`` (the model call).
    """

    def __init__(self, run_fixture=None, export_fixture=None,
                 models_listing=MODELS_LISTING, models_exit=0):
        self.run_fixture = run_fixture
        self.export_fixture = export_fixture
        self.models_listing = models_listing
        self.models_exit = models_exit
        self.calls = []

    def __call__(self, argv, *, cwd, timeout, env, max_output_bytes,
                 cancel_event=None):
        argv = [str(part) for part in argv]
        record = {"argv": list(argv), "cwd": cwd, "timeout": timeout,
                  "env": dict(env), "max_output_bytes": max_output_bytes}
        try:
            record["transport_config"] = (Path(cwd) / "opencode.json").read_text(
                encoding="utf-8")
        except OSError:
            record["transport_config"] = None
        _record_prompt_input(argv, record)
        self.calls.append(record)
        if len(argv) > 1 and argv[1] == "models":
            return CommandResult(argv=argv, exit_code=self.models_exit,
                                 duration_seconds=0.01, timed_out=False,
                                 output_overflow=False,
                                 stdout=(self.models_listing or "").encode(),
                                 stderr=b"")
        if len(argv) > 2 and argv[1:3] == ["session", "export"]:
            stdout = self.export_fixture
            if callable(stdout):
                stdout = stdout(argv[-1])
            return CommandResult(argv=argv, exit_code=0, duration_seconds=0.01,
                                 timed_out=False, output_overflow=False,
                                 stdout=_rebind_export_agent(stdout, cwd),
                                 stderr=b"")
        stdout = self.run_fixture
        if callable(stdout):
            stdout = stdout(_prompt_from_argv(argv))
        return CommandResult(argv=argv, exit_code=0, duration_seconds=0.01,
                             timed_out=False, output_overflow=False,
                             stdout=stdout or b"", stderr=b"")

    @property
    def prompts(self):
        return [call["prompt"] for call in self.calls
                if len(call["argv"]) > 1 and call["argv"][1] == "run"]

    @property
    def runs(self):
        return [call for call in self.calls
                if len(call["argv"]) > 1 and call["argv"][1] == "run"]

    @property
    def exports(self):
        return [call for call in self.calls
                if len(call["argv"]) > 2
                and call["argv"][1:3] == ["session", "export"]]

    @property
    def readiness_probes(self):
        return [call for call in self.calls
                if len(call["argv"]) > 1 and call["argv"][1] == "models"]


class ScenarioRunner:
    """Serves router JSON, a tool envelope, final text, or an itinerary plan."""

    def __init__(self, *, final_text="Here is the cafe.", plan_text=None,
                 router_text='{"intent": "TRAVEL"}', chitchat_text="Hello!",
                 tool_envelope=None, tokens=None, model=REQUESTED):
        self.final_text = final_text
        self.router_text = router_text
        self.chitchat_text = chitchat_text
        self.plan_text = plan_text
        self.tool_envelope = tool_envelope
        self.tokens = tokens or DEFAULT_TOKENS
        self.model = model
        self.calls = []
        self.exports = {}
        self._counter = 0

    def _next_ids(self):
        self._counter += 1
        n = self._counter
        return f"ses_test{n:04d}", f"msg_test{n:04d}"

    def _record(self, text, **kwargs):
        session, message = self._next_ids()
        self.exports[session] = json.dumps(
            export_payload(text, session, message, self.tokens, **kwargs)).encode()
        return event_text(text, session, message, self.tokens, **kwargs).encode()

    @property
    def runs(self):
        return [call for call in self.calls
                if len(call["argv"]) > 1 and call["argv"][1] == "run"]

    @property
    def export_calls(self):
        return [call for call in self.calls
                if len(call["argv"]) > 2
                and call["argv"][1:3] == ["session", "export"]]

    @property
    def readiness_probes(self):
        return [call for call in self.calls
                if len(call["argv"]) > 1 and call["argv"][1] == "models"]

    def __call__(self, argv, *, cwd, timeout, env, max_output_bytes,
                 cancel_event=None):
        argv = [str(part) for part in argv]
        record = {"argv": list(argv), "cwd": cwd, "timeout": timeout,
                  "env": dict(env), "max_output_bytes": max_output_bytes}
        try:
            record["transport_config"] = (Path(cwd) / "opencode.json").read_text(
                encoding="utf-8")
        except OSError:
            record["transport_config"] = None
        _record_prompt_input(argv, record)
        self.calls.append(record)
        if len(argv) > 1 and argv[1] == "models":
            return CommandResult(argv=argv, exit_code=0, duration_seconds=0.01,
                                 timed_out=False, output_overflow=False,
                                 stdout=MODELS_LISTING.encode(), stderr=b"")
        if len(argv) > 2 and argv[1:3] == ["session", "export"]:
            return CommandResult(argv=argv, exit_code=0, duration_seconds=0.01,
                                 timed_out=False, output_overflow=False,
                                 stdout=_rebind_export_agent(
                                     self.exports.get(argv[-1], b""), cwd),
                                 stderr=b"")
        prompt = _prompt_from_argv(argv)
        if ROUTER_MARKER in prompt:
            text = self.router_text
        elif SYNTHESIS_MARKER in prompt:
            text = self.plan_text or "{}"
        elif TOOL_PROTOCOL in prompt and TOOL_RESULT not in prompt:
            text = self.tool_envelope or json.dumps({
                "tool_calls": [{
                    "id": "call_1",
                    "name": "get_poi_details",
                    "arguments": {"poi_id": "poi_a"},
                }]
            })
        elif TOOL_PROTOCOL in prompt:
            text = self.final_text
        else:
            text = self.chitchat_text
        return CommandResult(argv=argv, exit_code=0, duration_seconds=0.01,
                             timed_out=False, output_overflow=False,
                             stdout=self._record(text), stderr=b"")


# ---------------------------------------------------------------------------
# MCP stand-ins for the actual main-module paths
# ---------------------------------------------------------------------------
class _Text:
    def __init__(self, text):
        self.text = text


class ToolResult:
    def __init__(self, text=None, is_error=False):
        self.isError = is_error
        self.content = [] if text is None else [_Text(text)]


def ok_json(payload):
    return ToolResult(json.dumps(payload))


class _MCPTool:
    def __init__(self, name, description="d", schema=None):
        self.name = name
        self.description = description
        self.inputSchema = schema or {"type": "object"}


class _MCPToolList:
    def __init__(self, tools):
        self.tools = tools


class FakeChatMCPSession:
    def __init__(self, tools=("get_poi_details",), handlers=None):
        self.tools = list(tools)
        self.handlers = handlers or {
            "get_poi_details": lambda args: ok_json({
                "success": True,
                "result": {"POI_ID": "poi_a", "POI_Name": "A"},
            }),
        }
        self.calls = []

    async def initialize(self):
        return None

    async def list_tools(self):
        schema = {"type": "object",
                  "properties": {"poi_id": {"type": "string"}},
                  "required": ["poi_id"]}
        return _MCPToolList([_MCPTool(name, schema=schema)
                             for name in self.tools])

    async def call_tool(self, name, arguments=None):
        self.calls.append({"tool": name, "args": dict(arguments or {})})
        return self.handlers[name](arguments or {})


def mcp_seam(session):
    @asynccontextmanager
    async def _seam():
        yield session

    return _seam


DEFAULT_ADMIN_CONTEXT = {
    "city_id": "hcmc", "district_id": "quan_1",
    "city_name": "Ho Chi Minh City", "district_name": "District 1",
}


def poi_evidence(poi_id="poi_a", name="Verified Cafe A"):
    return {
        "POI_ID": poi_id, "POI_Name": name,
        "POI_Address": "12 Le Loi, Quan 1, Ho Chi Minh City",
        "POI_Category": "Cafe", "latitude": 10.77, "longitude": 106.7,
        "POI_Description": {"insight": "", "seo_article": "",
                            "review": {"rating": 0.0, "review": ""}},
        "POI_Contact_Info": {"website": "", "fanpage": "",
                             "phonenumber": ""},
        "Offers": [], "NEAR_BY": [],
        "administrative_context": dict(DEFAULT_ADMIN_CONTEXT),
    }


def itinerary_handlers(candidates=("poi_a",)):
    def resolve(args):
        keyword = args.get("keyword", "")
        if "City" in keyword or "Ho Chi Minh" in keyword:
            return ok_json({"success": True, "matches": [
                {"type": "City", "id": "hcmc", "name": "Ho Chi Minh City"}]})
        return ok_json({"success": True, "matches": [
            {"type": "District", "id": "quan_1", "name": "District 1"}]})

    def categories(_args):
        return ok_json({"success": True, "categories": [
            {"id": "cat_coffee", "name": "Cafe"}]})

    def explore(_args):
        return ok_json({"success": True, "count": len(candidates),
                        "results": [{"id": pid} for pid in candidates]})

    def details(args):
        return ok_json({"success": True,
                        "result": poi_evidence(args.get("poi_id"))})

    def route(args):
        ids = args.get("ordered_poi_ids") or []
        return ok_json({"success": True, "distance_km": 1.0,
                        "time_minutes": 10.0, "stops_mapped": len(ids),
                        "stops": [{"id": pid, "latitude": 10.77,
                                   "longitude": 106.7} for pid in ids],
                        "turn_by_turn": []})

    return {
        "resolve_geographic_id": resolve,
        "get_available_categories": categories,
        "explore_pois": explore,
        "get_poi_details": details,
        "get_itinerary_route": route,
    }


def plan_text():
    return json.dumps({
        "start_poi_id": "poi_a", "end_poi_id": "poi_a",
        "total_estimated_budget": 55000.0,
        "stops": [{
            "date": "2026-01-01",
            "visit_time": "2026-01-01T09:00:00+07:00",
            "end_time": "2026-01-01T11:00:00+07:00",
            "description": "model free text",
            "budget": 55000.0,
            "poi": {"id": "poi_a"},
        }],
    })


class ItineraryMCPSession:
    def __init__(self, handlers):
        self.handlers = handlers
        self.calls = []

    async def initialize(self):
        return None

    async def call_tool(self, name, arguments=None):
        self.calls.append({"tool": name, "args": dict(arguments or {})})
        return self.handlers[name](arguments or {})


def snapshot(value):
    return copy.deepcopy(value)


def python_executable():
    return sys.executable
