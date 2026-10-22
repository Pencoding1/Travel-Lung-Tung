# Native core-service launcher (CORE-069 R2)

`core_service.py` start/status/stop hai service do task này tạo, chỉ trên
loopback:

| Service | Module | Địa chỉ |
| --- | --- | --- |
| POI MCP (SSE) | `app.api.mcp.tools` | `127.0.0.1:19101` |
| AI (uvicorn) | `uvicorn main:app` | `127.0.0.1:19102` |

## Interpreter và bootstrap

- Child luôn là **base interpreter** (`C:\Python314\python.exe`), không phải
  redirector `.venv-mcp-validation\Scripts\python.exe`. Nếu `--python` trỏ vào
  venv, helper đọc `pyvenv.cfg` để lấy base; helper không launch redirector.
- Argv cố định: `base\python.exe -s -c <bootstrap> <module> [args]`.
  Bootstrap đặt `sys.path` theo thứ tự: primary
  `.venv-mcp-validation\Lib\site-packages`, service root, repo root,
  `shared_lib`, rồi append `.venv\Lib\site-packages` cuối cho `tenacity`.
  Không dùng `PYTHONPATH`, không cài/copy package, không sửa `.env`/config.
- Trước khi spawn, helper kiểm SHA base (`467014...`) và chạy fingerprint
  one-shot: Python 3.14.x, MCP 1.26.0, neo4j 6.4.0, primary site đứng đầu.

## Lệnh

```powershell
# Từ root repo; helper tự resolve base interpreter
.venv-mcp-validation\Scripts\python.exe scripts\native_runtime\core_service.py start

.venv-mcp-validation\Scripts\python.exe scripts\native_runtime\core_service.py status

.venv-mcp-validation\Scripts\python.exe scripts\native_runtime\core_service.py stop
```

Tùy chọn: `--mcp-port`, `--ai-port`, `--alias`, `--executable`, `--python`,
`--state-file`, `--timeout`. Alias Go explicit (không đổi default AIbox):

```powershell
.venv-mcp-validation\Scripts\python.exe scripts\native_runtime\core_service.py start --alias opencode-go/deepseek-v4.1-flash
```

- UI: `http://127.0.0.1:19102/travel`
- Health AI: `GET /healthz`; MCP kiểm bằng SSE `200 text/event-stream`.

## Cấu hình per-run (cố định, không đọc secret)

- MCP: `MCP_HOST=127.0.0.1`, `MCP_PORT=<mcp>`,
  `POI_DB_SETTINGS_SOURCE=process_only`, `MEMGRAPH_HOST=127.0.0.1`,
  `MEMGRAPH_PORT=17687`, `MEMGRAPH_USER=""`, `MEMGRAPH_PASSWORD=""`,
  `FIRESTORE_ENABLED=false`, GraphHopper `127.0.0.1:18989`, profiles `car,foot`.
- AI: `MCP_SERVER_URL=http://127.0.0.1:<mcp>/sse`,
  `AI_LLM_PROVIDER=opencode_cli`, exact alias/executable, `AI_CLI_PURE=false`
  (installed CLI không có `--pure`; default provider vẫn fail-closed),
  `AI_CLI_MAX_ATTEMPTS=1`, `JEV_MODEL=jev-1.13.0`,
  `JEV_MIN_CONFIDENCE=0.69`.
- Với alias exact `opencode-go/deepseek-v4.1-flash`, config per-call chỉ ghi
  reference `{env:OPENCODE_API}`. Loader app đọc process env trước; nếu absent
  mới đọc đúng một key `OPENCODE_API` từ `.env` ở project root (bounded UTF-8,
  không interpolation). Key chỉ vào child env của CLI Go (readiness/run/export),
  không vào MCP/service khác, argv, state, config file hay report. Explicit
  blank/invalid fail constant, không fallback file.
- Chỉ allowlist biến OS được kế thừa. Hai guard carrier
  `OPENCODE_CONFIG_CONTENT`/`OPENCODE_CONFIG` được copy byte-exact (kể cả
  chuỗi rỗng); service override carrier bị từ chối trước `Popen`.

## Settings process-only

`POI_service/app/core/config/settings.py` chọn nguồn bằng biến literal:

| `POI_DB_SETTINGS_SOURCE` | Hành vi |
| --- | --- |
| absent hoặc `legacy_env_file` | giữ nguyên `MemgraphDB()` đọc `.env` như cũ |
| `process_only` | `MemgraphDB.from_process_env()`, không đọc `.env` |
| giá trị khác | fail `invalid_db_settings_source` trước khi load file |

Helper dùng `process_only`; actual owned Memgraph loopback không auth nên
user/password là chuỗi rỗng.

## Ownership, state và cleanup

- State ghi `pid`, `creation_time`, image path/SHA, module/args, bootstrap hash,
  port, health. Readiness yêu cầu listener owner **đúng PID đã spawn**.
- Không có freshness/adoption: listener lạ, PID reuse, creation/image/command
  mismatch, thiếu identity hoặc port thuộc process khác đều nhận **0 signal**.
- Stop chỉ signal sau khi mở handle mới và đối chiếu lại creation time; chỉ
  stop child do task tạo. Legacy R1 (venv redirector parent + base child) chỉ
  được reconcile khi đủ proof; nếu thiếu thì giữ nguyên state và trả
  `legacy_state_unverified`.
- Start lỗi chỉ cleanup process vừa spawn. Nếu cleanup không chứng minh được,
  giữ partial state, không xóa evidence và không claim closed.
- State/history không chứa env, header, JWT, password hay raw `.env`.
