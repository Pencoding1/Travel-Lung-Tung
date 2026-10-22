import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

ROOT = os.environ.get("TVLT_ROOT", "/mnt/e/Project/TVLT_2026")
GH = os.path.join(ROOT, ".runtime-native/graphhopper-11.1")
JRE = os.path.join(ROOT, ".runtime-native/java-21.0.12.1")
STATE = os.path.join(GH, "state")
OWNER = os.path.join(STATE, "owner.env")
JAR = os.path.join(GH, "download/graphhopper-web-11.1.jar")
JRE_ARCHIVE = os.path.join(JRE, "download/OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz")
JAVA = os.path.join(JRE, "root/jdk-21.0.12.1+1-jre/bin/java")
CONFIG = os.path.join(GH, "config/config.yml")
PBF = os.path.join(ROOT, "graphhopper/data/hcmc-latest.osm.pbf")
EXISTING_CONFIG = os.path.join(ROOT, "graphhopper/data/config.yml")
CACHE = os.path.join(GH, "graph-cache")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_owner():
    out = {}
    with open(OWNER, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
    return out


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def http_get(url):
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return {"http_status": r.status, "body": r.read().decode("utf-8", "replace")}
    except urllib.error.HTTPError as e:
        return {"http_status": e.code, "body": e.read().decode("utf-8", "replace")}
    except Exception as e:
        return {"http_status": None, "error": str(e)}


owner = read_owner()
pid = int(owner["PID"])
proc = "/proc/%d" % pid
stat_fields = read_text(proc + "/stat").split()
proc_starttime = stat_fields[21]
status_text = read_text(proc + "/status") or ""
vm = {}
for line in status_text.splitlines():
    if ":" in line:
        k, v = line.split(":", 1)
        vm[k.strip()] = v.strip()
cmdline = read_text(proc + "/cmdline").replace("\x00", " ").strip()
listeners = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True).stdout
own_listeners = [line.strip() for line in listeners.splitlines() if "pid=%d" % pid in line]
cache_files = []
for name in sorted(os.listdir(CACHE)):
    path = os.path.join(CACHE, name)
    if os.path.isfile(path):
        cache_files.append({"name": name, "bytes": os.path.getsize(path), "sha256": sha256(path)})

info = http_get("http://127.0.0.1:18989/info")
try:
    info_json = json.loads(info["body"]) if info.get("http_status") == 200 else None
except Exception:
    info_json = None

with open(os.path.join(STATE, "routes-summary.json"), "r", encoding="utf-8-sig") as f:
    routes = json.load(f)

windows_health = read_text(os.path.join(STATE, "health-windows.txt"))
windows_info_health = read_text(os.path.join(STATE, "info-health-windows.txt"))
windows_admin_health = read_text(os.path.join(STATE, "admin-health-windows.txt"))
windows_info = read_text(os.path.join(STATE, "info-windows.json"))

mem = subprocess.run(["free", "-m"], capture_output=True, text=True).stdout
disk = subprocess.run(["df", "-B1", ROOT], capture_output=True, text=True).stdout

java_version = subprocess.run(
    [JAVA, "-version"], capture_output=True, text=True,
    env={"HOME": os.path.join(JRE, "home"), "TMPDIR": os.path.join(JRE, "tmp"), "PATH": "/usr/bin:/bin"}
)
java_version_text = (java_version.stderr or "") + (java_version.stdout or "")

manifest = {
    "task_id": "OC-042",
    "executor_session_id": "ses_eb5ca6622ffedFZk0bZp4mO0yj",
    "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "engine": "GraphHopper 11.1 (patched per GHSA-mg8w-mq9r-f9c6)",
    "runtime": {
        "platform": "WSL2 Ubuntu 24.04.3 x86_64",
        "linux_pid": pid,
        "ownership_token": owner.get("TOKEN"),
        "proc_starttime_ticks": proc_starttime,
        "recorded_starttime_ticks": owner.get("STARTTIME"),
        "exe": os.readlink(proc + "/exe"),
        "cwd": os.readlink(proc + "/cwd"),
        "cmdline": cmdline,
        "vm": vm,
        "threads": len(os.listdir(proc + "/task")),
        "listeners": own_listeners,
        "health_live": http_get("http://127.0.0.1:18989/health"),
        "info_live": info,
        "info_health_live": http_get("http://127.0.0.1:18989/info/health"),
        "admin_healthcheck_live": http_get("http://127.0.0.1:18990/healthcheck"),
        "free_m": mem.strip(),
        "disk_bytes": disk.strip(),
        "windows_launcher_pid_latest": 35264,
        "windows_wslrelay_pid": 32972,
        "windows_host_evidence": {
            "health_http": 200,
            "health_body": windows_health,
            "info_health_http": 404,
            "info_health_body": windows_info_health,
            "admin_healthcheck_http": 200,
            "admin_healthcheck_body": windows_admin_health,
            "info_http": 200,
        },
    },
    "artifacts": {
        "graphhopper_jar": {
            "source_url": "https://repo.maven.apache.org/maven2/com/graphhopper/graphhopper-web/11.1/graphhopper-web-11.1.jar",
            "file": JAR,
            "bytes": os.path.getsize(JAR),
            "sha256": sha256(JAR),
            "sha1_file": read_text(JAR + ".sha1"),
            "sha256_file": read_text(JAR + ".sha256"),
            "sha512_file": read_text(JAR + ".sha512"),
            "manifest_version": "11.1",
            "pom_version": "11.1",
            "build_jdk": "17.0.20.1",
        },
        "jre": {
            "source_url": "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz",
            "file": JRE_ARCHIVE,
            "bytes": os.path.getsize(JRE_ARCHIVE),
            "sha256": sha256(JRE_ARCHIVE),
            "vendor_checksum_sha256": "2413149700df0f7d440500a84a8f764c535f21e5a5e87d38328b64eec2c5b500",
            "vendor_checksum_file": read_text(os.path.join(JRE, "download/sha256.txt")),
            "signature_file": os.path.join(JRE, "download/signature.sig"),
            "signature_verified": False,
            "java_path": JAVA,
            "java_sha256": sha256(JAVA),
            "java_version": java_version_text.strip(),
            "archive_entries": 320,
            "archive_files": 112,
            "archive_dirs": 63,
            "archive_symlinks": 145,
            "archive_symlink_targets_inside_tree": True,
            "archive_device_fifo_hardlink_entries": 0,
            "archive_install_scripts": 0,
        },
        "pbf": {
            "file": PBF,
            "bytes": os.path.getsize(PBF),
            "sha256_before": "c2b7057e7a022ff929692205e4219c59640fc67fd90525a82428022b43cf4afb",
            "sha256_after": sha256(PBF),
        },
        "existing_config_readonly": {
            "file": EXISTING_CONFIG,
            "sha256": sha256(EXISTING_CONFIG),
        },
        "own_config": {
            "file": CONFIG,
            "sha256": sha256(CONFIG),
        },
        "graph_cache": {
            "dir": CACHE,
            "fresh_import_started_at_utc": "2026-10-17T14:22:02Z",
            "files": cache_files,
        },
    },
    "engine_info": info_json,
    "routes_summary": routes,
    "lifecycle": {
        "duplicate_start_exit": 10,
        "duplicate_start_effect": "refused; existing owned process untouched",
        "owned_stop_pid": 2296,
        "owned_stop_result": "stopped_owned",
        "ports_free_after_stop": True,
        "restart_windows_launcher_pid": 35264,
        "restart_ready_after_ms": 10166,
        "restart_linux_pid": pid,
        "final_status": "running_owned_healthy",
    },
    "startup_attempts": [
        {
            "attempt": 1,
            "result": "failed before import",
            "cause": "GraphHopper 11.1 requires explicit import.osm.ignored_highways property",
            "correction": "set import.osm.ignored_highways: construction to retain footways for foot profile",
        },
        {
            "attempt": 2,
            "result": "engine imported and listened on 127.0.0.1:18989/18990 but readiness helper queried absent /info/health and timed out",
            "cause": "GraphHopper 11.1 exposes /health and /info, not /info/health",
            "correction": "readiness now uses /health; /info/health 404 is recorded as endpoint fact",
        },
        {
            "attempt": 3,
            "result": "Windows host could not reach loopback relay (empty reply on IPv6-mapped listener)",
            "cause": "Java bound IPv6-mapped loopback and WSL localhost relay exposed broken IPv6 path on this host",
            "correction": "added per-process -Djava.net.preferIPv4Stack=true; Windows 127.0.0.1 then returned HTTP 200",
        },
        {
            "attempt": 4,
            "result": "success",
            "cause": None,
            "correction": None,
        },
    ],
    "limits": [
        "Not Docker/Compose, primary import, H2/H3, application integration, benchmark, route optimality, or full-goal acceptance.",
        "Engine profile support is not application compatibility: the application still targets GraphHopper port 8989 and configures only the car profile.",
        "No elevation data; graph is 2D and foot_elevation.json is not used.",
        "JRE detached signature was downloaded but not cryptographically verified; vendor SHA-256 file matched actual bytes.",
        "OSM data date is 2026-03-17T23:00Z; no newer snapshot was fetched.",
        "No online or mock routing fallback was used.",
    ],
}

os.makedirs(STATE, exist_ok=True)
out = os.path.join(STATE, "runtime-manifest.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)
print(out)
print(json.dumps({
    "pid": pid,
    "rss": vm.get("VmRSS"),
    "hwm": vm.get("VmHWM"),
    "threads": manifest["runtime"]["threads"],
    "listeners": own_listeners,
    "health": manifest["runtime"]["health_live"],
    "info_health": manifest["runtime"]["info_health_live"],
    "admin": manifest["runtime"]["admin_healthcheck_live"],
    "pbf_after": manifest["artifacts"]["pbf"]["sha256_after"],
}, indent=2))
