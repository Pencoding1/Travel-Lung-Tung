#!/usr/bin/env bash
# OC-041 isolated workspace-native Memgraph runtime helper (Ubuntu WSL).
# Never installs packages, never touches system services, never uses historical data.
set -euo pipefail

WS="${TVLT_WORKSPACE:-/mnt/e/Project/TVLT_2026}"
RT="$WS/.runtime-native"
DOWNLOAD="$RT/download"
MG_DIR="$RT/memgraph-3.13.2"
ROOT="$MG_DIR/root"
BIN="$ROOT/usr/lib/memgraph/memgraph"
DATA_DIR="$RT/data-edge-properties-v1"
DATA_MARKER="$RT/state/data-edge-properties-v1.owner"
LOG_DIR="$RT/logs"
HOME_DIR="$RT/home"
TMP_DIR="$RT/tmp"
STATE_DIR="$RT/state"
VENDOR_LIB="$RT/vendor-lib"
ATOMIC_ROOT="$RT/system-libs/libatomic1"
ATOMIC_LIB="$ATOMIC_ROOT/usr/lib/x86_64-linux-gnu"
OWNER_FILE="$STATE_DIR/owner.json"
PID_FILE="$STATE_DIR/memgraph.pid"
TOKEN_FILE="$STATE_DIR/ownership_token"
MANIFEST="$MG_DIR/runtime-manifest.json"
SYSTEM_LIBPYTHON="/usr/lib/x86_64-linux-gnu/libpython3.12.so.1.0"

PKG_URL="https://download.memgraph.com/memgraph/v3.13.2/x86_64-deb/memgraph_3.13.2-1_amd64.deb"
PKG_FILE="$DOWNLOAD/memgraph_3.13.2-1_amd64.deb"
PKG_SIZE=43561700
PKG_SHA=e9e8ba25c045ca6641df3ef817d88ea4f34210fc7ba804eb617871f5e43f56fa

ATOMIC_VERSION="14.2.0-4ubuntu2~24.04.1"
ATOMIC_URL="https://archive.ubuntu.com/ubuntu/pool/main/g/gcc-14/libatomic1_14.2.0-4ubuntu2~24.04.1_amd64.deb"
ATOMIC_FILE="$DOWNLOAD/libatomic1_14.2.0-4ubuntu2~24.04.1_amd64.deb"
ATOMIC_SHA=fe49cbbc7be753528380c724a8eef5f1e31dffa9221f692c5069048d81c7449d

BOLT_ADDRESS=127.0.0.1
BOLT_PORT=17687
MONITORING_ADDRESS=127.0.0.1
MONITORING_PORT=17444
METRICS_ADDRESS=127.0.0.1
METRICS_PORT=19091
MEMORY_LIMIT_MIB=3072
EDGE_PROPERTIES=true

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

check_space() {
  local avail_kb
  avail_kb=$(df -Pk "$WS" | awk 'NR==2 {print $4}')
  [ "$avail_kb" -ge 614400 ] || die "Insufficient free space on workspace filesystem: ${avail_kb} KiB (need >= 614400 KiB)"
  log "Free space check OK: ${avail_kb} KiB available"
}

ensure_dirs() {
  mkdir -p "$DOWNLOAD" "$MG_DIR" "$LOG_DIR" "$HOME_DIR" "$TMP_DIR" "$STATE_DIR" "$VENDOR_LIB" "$ATOMIC_ROOT"
}

prepare_data_dir() {
  local resolved_rt resolved_data
  resolved_rt=$(realpath -m "$RT")
  resolved_data=$(realpath -m "$DATA_DIR")
  case "$resolved_data" in
    "$resolved_rt"/*) ;;
    *) die "Data directory resolves outside the owned runtime root: $resolved_data" ;;
  esac
  if [ -e "$DATA_DIR" ] && [ -n "$(ls -A "$DATA_DIR" 2>/dev/null || true)" ]; then
    if [ ! -f "$DATA_MARKER" ] || [ "$(cat "$DATA_MARKER")" != "$(cat "$TOKEN_FILE")" ]; then
      die "Fresh edge-property data directory already exists nonempty without a matching ownership marker; refusing to reuse or delete: $DATA_DIR"
    fi
    log "Reusing owned edge-property data directory: $DATA_DIR"
    return 0
  fi
  mkdir -p "$DATA_DIR"
  printf '%s\n' "$(cat "$TOKEN_FILE")" > "$DATA_MARKER"
  log "Prepared fresh edge-property data directory: $DATA_DIR"
}

fetch_verified() {
  local url="$1" dest="$2" expected_sha="$3" label="$4" max_time="${5:-300}"
  local actual
  if [ -f "$dest" ]; then
    actual=$(sha256sum "$dest" | awk '{print $1}')
    if [ "$actual" = "$expected_sha" ]; then
      log "Reusing verified $label: $dest (sha256=$actual)"
      return 0
    fi
    die "Existing $label hash mismatch; preserving file and stopping. expected=$expected_sha actual=$actual path=$dest"
  fi
  local part="$dest.part-$$"
  log "Downloading $label from $url"
  curl --fail --location --silent --show-error \
    --proto '=https' --tlsv1.2 \
    --retry 3 --retry-delay 2 --connect-timeout 20 --max-time "$max_time" \
    --max-filesize 268435456 \
    --output "$part" "$url"
  actual=$(sha256sum "$part" | awk '{print $1}')
  [ "$actual" = "$expected_sha" ] || die "$label SHA256 mismatch: expected=$expected_sha actual=$actual (partial kept at $part)"
  mv "$part" "$dest"
  log "Downloaded $label ($(stat -c %s "$dest") bytes, sha256=$actual)"
}

validate_archive() {
  local deb="$1"
  python3 - "$deb" <<'PY'
import posixpath
import subprocess
import sys

deb = sys.argv[1]
listing = subprocess.check_output(["dpkg-deb", "-c", deb], text=True)
problems = []
entries = 0
for line in listing.splitlines():
    if not line.strip():
        continue
    parts = line.split(None, 5)
    if len(parts) < 6:
        problems.append("unparsable listing line: " + line)
        continue
    mode, _owner, _size, _date, _time, path = parts
    entries += 1
    if path.startswith("/") or not path.startswith("./"):
        problems.append("non-relative path: " + path)
        continue
    norm = posixpath.normpath(path)
    if norm == ".." or norm.startswith("../") or norm.startswith("/"):
        problems.append("path traversal: " + path)
        continue
    if mode.startswith("l") and " -> " in path:
        link_path, target = path.split(" -> ", 1)
        if target.startswith("/"):
            problems.append("absolute symlink target: %s -> %s" % (link_path, target))
            continue
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(link_path), target))
        if resolved.startswith("../") or resolved.startswith("/"):
            problems.append("symlink escapes tree: %s -> %s" % (link_path, target))
if problems:
    print("UNSAFE ARCHIVE:")
    for p in problems:
        print("  " + p)
    sys.exit(1)
print("Archive path/symlink validation OK (%d entries, no absolute/traversal escapes)" % entries)
PY
}

extract_package() {
  local deb="$1"
  if [ -x "$BIN" ]; then
    log "Reusing existing extracted package tree: $ROOT"
    return 0
  fi
  if [ -d "$ROOT" ] && [ -n "$(ls -A "$ROOT" 2>/dev/null || true)" ]; then
    die "Extraction target exists and is not empty but binary is missing: $ROOT"
  fi
  mkdir -p "$ROOT"
  dpkg-deb -x "$deb" "$ROOT"
  [ -x "$BIN" ] || die "Extraction did not produce expected binary: $BIN"
  log "Extracted package without installation into $ROOT"
}

ensure_libraries() {
  [ -f "$SYSTEM_LIBPYTHON" ] || die "Missing system library base: $SYSTEM_LIBPYTHON (cannot create per-process libpython3.so link)"
  if [ ! -L "$VENDOR_LIB/libpython3.so" ]; then
    ln -s "$SYSTEM_LIBPYTHON" "$VENDOR_LIB/libpython3.so"
  fi
  [ -f "$ATOMIC_LIB/libatomic.so.1" ] || die "Missing extracted libatomic runtime: $ATOMIC_LIB/libatomic.so.1"
  log "Per-process library path prepared (libpython3.so -> system libpython3.12; extracted libatomic1)"
}

write_manifest() {
  local now token
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  token=$(cat "$TOKEN_FILE")
  export OC041_NOW="$now" OC041_TOKEN="$token" OC041_WS="$WS" OC041_RT="$RT"
  export OC041_PKG_URL="$PKG_URL" OC041_PKG_SHA="$PKG_SHA" OC041_PKG_SIZE="$PKG_SIZE"
  export OC041_ATOMIC_VERSION="$ATOMIC_VERSION" OC041_ATOMIC_URL="$ATOMIC_URL" OC041_ATOMIC_SHA="$ATOMIC_SHA"
  export OC041_MANIFEST="$MANIFEST" OC041_BIN="$BIN" OC041_ROOT="$ROOT"
  export OC041_DATA="$DATA_DIR" OC041_LOG="$LOG_DIR" OC041_HOME="$HOME_DIR" OC041_STATE="$STATE_DIR"
  export OC041_BOLT_ADDRESS="$BOLT_ADDRESS" OC041_BOLT_PORT="$BOLT_PORT"
  export OC041_MON_ADDRESS="$MONITORING_ADDRESS" OC041_MON_PORT="$MONITORING_PORT"
  export OC041_MET_ADDRESS="$METRICS_ADDRESS" OC041_MET_PORT="$METRICS_PORT"
  export OC041_MEMLIMIT="$MEMORY_LIMIT_MIB" OC041_EDGE_PROPERTIES="$EDGE_PROPERTIES" OC041_DISTRO="$(. /etc/os-release; echo "$PRETTY_NAME")" OC041_KERNEL="$(uname -r)"
  python3 - <<'PY'
import hashlib, json, os, platform
m = os.environ
def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
manifest = {
    "run_id": "OC-046",
    "supersedes_run_id": "OC-041",
    "ownership_token": m["OC041_TOKEN"],
    "prepared_at_utc": m["OC041_NOW"],
    "workspace": m["OC041_WS"],
    "host": {
        "wsl_distro": m["OC041_DISTRO"],
        "kernel": m["OC041_KERNEL"],
        "user": os.environ.get("USER", "duyan"),
        "windows_host": platform.node(),
    },
    "memgraph": {
        "version": "3.13.2",
        "package_url": m["OC041_PKG_URL"],
        "package_sha256": m["OC041_PKG_SHA"],
        "package_size_bytes": int(m["OC041_PKG_SIZE"]),
        "package_verification": "locally computed SHA256 and exact content-length match; no publisher checksum file published at the direct-download URL",
        "extracted_root": m["OC041_ROOT"],
        "binary_path": m["OC041_BIN"],
        "binary_sha256": sha(m["OC041_BIN"]),
        "installation": "dpkg-deb -x only; no postinst/systemd/apt/system-wide install",
    },
    "dependency_supplements": {
        "libpython3.so": {
            "resolution": "per-process symlink to existing system libpython3.12.so.1.0",
            "target": "/usr/lib/x86_64-linux-gnu/libpython3.12.so.1.0",
        },
        "libatomic.so.1": {
            "version": m["OC041_ATOMIC_VERSION"],
            "url": m["OC041_ATOMIC_URL"],
            "sha256": m["OC041_ATOMIC_SHA"],
            "extracted_to": m["OC041_RT"] + "/system-libs/libatomic1",
            "system_installed": False,
            "reason": "not present on the host; extracted only for per-process LD_LIBRARY_PATH use",
        },
    },
    "runtime": {
        "data_dir": m["OC041_DATA"],
        "log_dir": m["OC041_LOG"],
        "home_dir": m["OC041_HOME"],
        "state_dir": m["OC041_STATE"],
        "storage_mode": "IN_MEMORY_TRANSACTIONAL",
        "storage_properties_on_edges": m["OC041_EDGE_PROPERTIES"] == "true",
        "relationship_properties": m["OC041_EDGE_PROPERTIES"] == "true",
        "memory_limit_mib": int(m["OC041_MEMLIMIT"]),
        "telemetry_enabled": False,
        "bindings": {
            "bolt": m["OC041_BOLT_ADDRESS"] + ":" + m["OC041_BOLT_PORT"],
            "monitoring": m["OC041_MON_ADDRESS"] + ":" + m["OC041_MON_PORT"],
            "metrics": m["OC041_MET_ADDRESS"] + ":" + m["OC041_MET_PORT"],
        },
        "query_modules_directory": "(default built-in only; no extracted query modules loaded)",
    },
}
with open(m["OC041_MANIFEST"], "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
print("Wrote manifest:", m["OC041_MANIFEST"])
PY
}

prepare() {
  check_space
  ensure_dirs
  if [ ! -f "$TOKEN_FILE" ]; then
    printf 'oc041-%s-%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')" > "$TOKEN_FILE"
  fi
  prepare_data_dir
  fetch_verified "$PKG_URL" "$PKG_FILE" "$PKG_SHA" "Memgraph 3.13.2 DEB"
  [ "$(stat -c %s "$PKG_FILE")" -eq "$PKG_SIZE" ] || die "Package size mismatch: $(stat -c %s "$PKG_FILE") != $PKG_SIZE"
  validate_archive "$PKG_FILE"
  extract_package "$PKG_FILE"
  fetch_verified "$ATOMIC_URL" "$ATOMIC_FILE" "$ATOMIC_SHA" "libatomic1 ${ATOMIC_VERSION} DEB" 120
  if [ ! -f "$ATOMIC_LIB/libatomic.so.1" ]; then
    dpkg-deb -x "$ATOMIC_FILE" "$ATOMIC_ROOT"
  fi
  ensure_libraries
  LD_LIBRARY_PATH="$VENDOR_LIB:$ATOMIC_LIB:$ROOT/usr/lib/memgraph" ldd "$BIN" > "$STATE_DIR/ldd.txt" 2>&1 || true
  if grep -q "not found" "$STATE_DIR/ldd.txt"; then
    cat "$STATE_DIR/ldd.txt" >&2
    die "Unresolved shared library remains"
  fi
  write_manifest
  log "Prepare complete. Binary: $BIN"
}

proc_start_ticks() {
  local pid="$1"
  python3 - "$pid" <<'PY'
import sys
pid = sys.argv[1]
with open("/proc/%s/stat" % pid, "r", encoding="utf-8", errors="replace") as f:
    raw = f.read()
    tail = raw[raw.rfind(")") + 2:].split()
    print(tail[19])
PY
}

owner_field() {
  python3 - "$OWNER_FILE" "$1" <<'PY'
import json, sys
try:
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        print(json.load(f).get(sys.argv[2], ""))
except FileNotFoundError:
    print("")
PY
}

verify_ownership() {
  local pid="$1"
  [ -n "$pid" ] || { echo "no recorded PID"; return 1; }
  [ -d "/proc/$pid" ] || { echo "PID $pid is not running"; return 1; }
  local exe recorded_exe ticks recorded_ticks cmd data_dir recorded_data
  exe=$(readlink -f "/proc/$pid/exe" 2>/dev/null || true)
  recorded_exe=$(owner_field executable)
  [ "$exe" = "$recorded_exe" ] || { echo "executable mismatch: running=$exe recorded=$recorded_exe"; return 1; }
  ticks=$(proc_start_ticks "$pid")
  recorded_ticks=$(owner_field proc_start_ticks)
  [ "$ticks" = "$recorded_ticks" ] || { echo "process start-time mismatch: $ticks != $recorded_ticks"; return 1; }
  cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline")
  recorded_data=$(owner_field data_dir)
  printf '%s' "$cmd" | grep -Fq -- "--data-directory=$recorded_data" || { echo "data-directory fingerprint missing from cmdline"; return 1; }
  printf '%s' "$cmd" | grep -Fq -- "--bolt-port=$BOLT_PORT" || { echo "bolt-port fingerprint missing from cmdline"; return 1; }
  [ "$(owner_field ownership_token)" = "$(cat "$TOKEN_FILE")" ] || { echo "ownership token mismatch"; return 1; }
  return 0
}

is_running() {
  local pid
  pid=$(cat "$PID_FILE" 2>/dev/null || true)
  [ -n "$pid" ] && [ -d "/proc/$pid" ] || return 1
  verify_ownership "$pid" >/dev/null 2>&1
}

wait_ready() {
  local pid="$1" i
  for i in $(seq 1 60); do
    [ -d "/proc/$pid" ] || return 1
    if python3 - <<'PY'
import socket, sys
s = socket.socket()
s.settimeout(1)
try:
    s.connect(("127.0.0.1", 17687))
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
    then
      return 0
    fi
    sleep 1
  done
  return 1
}

start() {
  prepare
  local pid
  if is_running; then
    pid=$(cat "$PID_FILE")
    log "Runtime already running under verified ownership (pid=$pid); not starting a duplicate"
    status
    return 0
  fi
  if ss -ltn | grep -Eq ':17687[[:space:]]'; then
    die "Port 17687 is already occupied; refusing to start rather than reusing or killing it"
  fi
  rm -f "$PID_FILE"
  local started_at token
  started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  token=$(cat "$TOKEN_FILE")
  : > "$LOG_DIR/memgraph.stdout.log"
  log "Starting owned Memgraph 3.13.2 (bolt 127.0.0.1:$BOLT_PORT, data=$DATA_DIR)"
  setsid env -i \
    PATH=/usr/local/bin:/usr/bin:/bin \
    HOME="$HOME_DIR" \
    TMPDIR="$TMP_DIR" \
    USER=duyan LOGNAME=duyan LANG=C.UTF-8 \
    LD_LIBRARY_PATH="$VENDOR_LIB:$ATOMIC_LIB:$ROOT/usr/lib/memgraph" \
    "$BIN" \
      --data-directory="$DATA_DIR" \
      --log-file="$LOG_DIR/memgraph.log" \
      --also-log-to-stderr \
      --log-level=INFO \
      --bolt-address="$BOLT_ADDRESS" \
      --bolt-port="$BOLT_PORT" \
      --monitoring-address="$MONITORING_ADDRESS" \
      --monitoring-port="$MONITORING_PORT" \
      --metrics-address="$METRICS_ADDRESS" \
      --metrics-port="$METRICS_PORT" \
      --telemetry-enabled=false \
      --memory-limit="$MEMORY_LIMIT_MIB" \
      --storage-properties-on-edges=true \
      --storage-mode=IN_MEMORY_TRANSACTIONAL \
      --storage-wal-enabled=true \
      --storage-snapshot-interval-sec=300 \
      --storage-snapshot-on-exit=true \
      --data-recovery-on-startup=true \
    >> "$LOG_DIR/memgraph.stdout.log" 2>&1 < /dev/null &
  pid=$!
  echo "$pid" > "$PID_FILE"
  sleep 1
  if ! [ -d "/proc/$pid" ]; then
    tail -40 "$LOG_DIR/memgraph.stdout.log" >&2 || true
    die "Memgraph process exited during startup (pid $pid)"
  fi
  local ticks cmd
  ticks=$(proc_start_ticks "$pid")
  cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline")
  export OC041_OWNER_FILE="$OWNER_FILE" OC041_PID="$pid" OC041_TICKS="$ticks" OC041_CMD="$cmd"
  export OC041_STARTED_AT="$started_at" OC041_TOKEN="$token" OC041_BIN="$BIN" OC041_DATA="$DATA_DIR"
  export OC041_BINARY_SHA="$(sha256sum "$BIN" | awk '{print $1}')" OC041_WSL_DISTRO="$(. /etc/os-release; echo "$PRETTY_NAME")"
  python3 - <<'PY'
import hashlib, json, os
m = os.environ
owner = {
    "run_id": "OC-046",
    "supersedes_run_id": "OC-041",
    "storage_properties_on_edges": True,
    "relationship_properties": True,
    "ownership_token": m["OC041_TOKEN"],
    "pid": int(m["OC041_PID"]),
    "proc_start_ticks": m["OC041_TICKS"],
    "executable": m["OC041_BIN"],
    "binary_sha256": m["OC041_BINARY_SHA"],
    "data_dir": m["OC041_DATA"],
    "command": m["OC041_CMD"].strip(),
    "command_sha256": hashlib.sha256(m["OC041_CMD"].strip().encode()).hexdigest(),
    "started_at_utc": m["OC041_STARTED_AT"],
    "launch_mode": "detached Linux setsid process under Ubuntu user; no Windows process owned by this task",
    "windows_pid": None,
    "wsl_distro": m["OC041_WSL_DISTRO"],
    "bolt_uri": "bolt://127.0.0.1:17687",
    "command_flags": {
        "storage_properties_on_edges": True,
    },
}
with open(m["OC041_OWNER_FILE"], "w", encoding="utf-8") as f:
    json.dump(owner, f, indent=2)
    f.write("\n")
PY
  if ! wait_ready "$pid"; then
    log "Readiness wait failed; capturing evidence"
    tail -80 "$LOG_DIR/memgraph.stdout.log" >&2 || true
    tail -80 "$LOG_DIR/memgraph.log" >&2 || true
    ss -ltnp > "$STATE_DIR/listeners-failed.txt" || true
    if verify_ownership "$pid" >/dev/null 2>&1; then
      log "Stopping failed owned instance safely"
      stop || true
    fi
    die "Memgraph did not become Bolt-ready on 127.0.0.1:$BOLT_PORT"
  fi
  ss -ltnp | grep -E ':(17687|17444|19091)[[:space:]]' > "$STATE_DIR/listeners.txt" || true
  {
    echo "started_at_utc=$started_at"
    echo "linux_pid=$pid"
    echo "proc_start_ticks=$ticks"
    echo "binary=$BIN"
    echo "binary_sha256=$(sha256sum "$BIN" | awk '{print $1}')"
    echo "data_dir=$DATA_DIR"
    echo "bolt_uri=bolt://127.0.0.1:17687"
    echo "ownership_token=$token"
    echo "command=$cmd"
  } > "$STATE_DIR/running-fingerprint.txt"
  log "Memgraph is Bolt-ready (linux_pid=$pid, uri=bolt://127.0.0.1:17687)"
  status
}

status() {
  local pid
  pid=$(cat "$PID_FILE" 2>/dev/null || true)
  if [ -z "$pid" ]; then
    log "STOPPED: no PID recorded"
    return 1
  fi
  if [ ! -d "/proc/$pid" ]; then
    log "STOPPED: recorded PID $pid is not running"
    return 1
  fi
  local v
  if ! v=$(verify_ownership "$pid"); then
    log "UNVERIFIED: PID $pid exists but ownership validation failed: $v"
    return 2
  fi
  local port_state
  port_state=$(ss -ltnp 2>/dev/null | grep -E ':(17687|17444|19091)[[:space:]]' || true)
  log "RUNNING: verified owned Memgraph pid=$pid uri=bolt://127.0.0.1:$BOLT_PORT"
  printf '%s\n' "$port_state"
  python3 - "$OWNER_FILE" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    o = json.load(f)
for k in ("ownership_token", "executable", "binary_sha256", "data_dir", "started_at_utc", "proc_start_ticks", "command_sha256", "bolt_uri"):
    print("%s=%s" % (k, o.get(k)))
PY
  return 0
}

stop() {
  local pid
  pid=$(cat "$PID_FILE" 2>/dev/null || true)
  [ -n "$pid" ] || { log "No recorded PID; nothing to stop"; return 0; }
  if [ ! -d "/proc/$pid" ]; then
    log "Recorded PID $pid is not running; leaving state files in place"
    return 0
  fi
  local v
  if ! v=$(verify_ownership "$pid"); then
    log "REFUSING to signal PID $pid: ownership validation failed: $v"
    return 2
  fi
  log "Sending SIGTERM to verified owned Memgraph pid=$pid"
  kill -TERM "$pid"
  # Bounded graceful shutdown: Memgraph writes an exit snapshot and drains the
  # WAL here, which takes longer than a trivial process exit. Never escalate to
  # SIGKILL: a timeout leaves the owned process and data intact for the caller.
  for _ in $(seq 1 180); do
    [ -d "/proc/$pid" ] || { log "Owned Memgraph stopped cleanly"; return 0; }
    sleep 1
  done
  log "ERROR: graceful stop did not finish within 180s; leaving verified owned pid=$pid and data untouched (no SIGKILL)"
  return 1
}

smoke_local() {
  "$ROOT/usr/bin/mgconsole" --host 127.0.0.1 --port "$BOLT_PORT" -e "RETURN 1 AS one;" 2>&1 || true
}

case "${1:-}" in
  prepare) prepare ;;
  start) start ;;
  status) status ;;
  stop) stop ;;
  smoke-local) smoke_local ;;
  *) echo "usage: $0 {prepare|start|status|stop|smoke-local}" >&2; exit 64 ;;
esac
