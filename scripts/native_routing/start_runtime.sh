#!/usr/bin/env bash
set -euo pipefail

ROOT="${TVLT_ROOT:-/mnt/e/Project/TVLT_2026}"
GH="$ROOT/.runtime-native/graphhopper-11.1"
JRE="$ROOT/.runtime-native/java-21.0.12.1"
JAVA="$JRE/root/jdk-21.0.12.1+1-jre/bin/java"
JAVA_REAL=$(readlink -f "$JAVA")
JAR="$GH/download/graphhopper-web-11.1.jar"
CONFIG="$GH/config/config.yml"
PBF="$ROOT/graphhopper/data/hcmc-latest.osm.pbf"
WORK="$GH/work"
PIDFILE="$GH/state/graphhopper.pid"
OWNER="$GH/state/owner.env"
LOGFILE="$GH/logs/console.log"

EXPECTED_PBF_SHA256="c2b7057e7a022ff929692205e4219c59640fc67fd90525a82428022b43cf4afb"
EXPECTED_JAR_SHA256="8462f758d9ea49edaded557cec5c687a0a24f004ec371cd4daaeb0534824ea33"

mkdir -p "$GH/download" "$GH/config" "$GH/work" "$GH/logs" "$GH/state" "$GH/home" "$GH/tmp" "$GH/graph-cache"
exec >> "$GH/logs/start.log" 2>&1

echo "started_at=$(date -Ins)"
echo "root=$ROOT"

if [ -f "$PIDFILE" ]; then
  OLD_PID=$(tr -dc '0-9' < "$PIDFILE")
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "REFUSE: owned runtime process already alive pid=$OLD_PID"
    exit 10
  fi
  echo "stale_pidfile=$OLD_PID"
fi

if ss -ltn | awk '{print $4}' | grep -Eq '(^|:)(18989|18990)$'; then
  echo "REFUSE: required loopback port already listening"
  ss -ltn | grep -E ':(18989|18990)[[:space:]]'
  exit 11
fi

[ -x "$JAVA_REAL" ] || { echo "REFUSE: java executable missing"; exit 12; }
[ -f "$JAR" ] || { echo "REFUSE: graphhopper jar missing"; exit 12; }
[ -f "$CONFIG" ] || { echo "REFUSE: config missing"; exit 12; }
[ -f "$PBF" ] || { echo "REFUSE: source pbf missing"; exit 12; }

PBF_SHA256=$(sha256sum "$PBF" | awk '{print $1}')
JAR_SHA256=$(sha256sum "$JAR" | awk '{print $1}')
echo "pbf_sha256=$PBF_SHA256"
echo "jar_sha256=$JAR_SHA256"
[ "$PBF_SHA256" = "$EXPECTED_PBF_SHA256" ] || { echo "REFUSE: pbf hash mismatch"; exit 13; }
[ "$JAR_SHA256" = "$EXPECTED_JAR_SHA256" ] || { echo "REFUSE: jar hash mismatch"; exit 13; }

TOKEN=$(python3 -c 'import uuid; print(uuid.uuid4().hex)')
START_STAMP=$(date -Ins)

cd "$WORK"
nohup env -u JAVA_TOOL_OPTIONS -u _JAVA_OPTIONS \
  HOME="$GH/home" TMPDIR="$GH/tmp" TMP="$GH/tmp" TEMP="$GH/tmp" \
  "$JAVA_REAL" -Xms256m -Xmx1024m -XX:+UseG1GC -Djava.net.preferIPv4Stack=true -Dfile.encoding=UTF-8 \
  -jar "$JAR" server "$CONFIG" >> "$LOGFILE" 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$PIDFILE"
echo "launched_linux_pid=$PID"
sleep 1
PID_STARTTIME=$(awk '{print $22}' "/proc/$PID/stat" 2>/dev/null || true)

check_owned_pid() {
  kill -0 "$PID" 2>/dev/null || return 1
  [ -n "$PID_STARTTIME" ] || return 1
  [ "$(awk '{print $22}' "/proc/$PID/stat" 2>/dev/null || true)" = "$PID_STARTTIME" ] || return 1
  [ "$(readlink "/proc/$PID/exe" 2>/dev/null || true)" = "$JAVA_REAL" ] || return 1
  [ "$(readlink "/proc/$PID/cwd" 2>/dev/null || true)" = "$WORK" ] || return 1
  CMD=$(tr '\0' ' ' < "/proc/$PID/cmdline" 2>/dev/null || true)
  case "$CMD" in
    *"$JAR"*"$CONFIG"*) return 0 ;;
    *) return 1 ;;
  esac
}

READY=0
for _ in $(seq 1 120); do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "process_exited_before_ready"
    break
  fi
  CODE=$(curl -sS -o "$GH/state/startup-health.json" -w '%{http_code}' --max-time 2 http://127.0.0.1:18989/health 2>/dev/null || true)
  if [ "$CODE" = "200" ]; then
    READY=1
    break
  fi
  sleep 5
done

if [ "$READY" -ne 1 ]; then
  echo "READINESS FAILED"
  tail -n 80 "$LOGFILE" || true
  if check_owned_pid; then
    echo "readiness_failure_owned_pid=$PID"
    if check_owned_pid; then
      kill -TERM "$PID" 2>/dev/null || true
      sleep 5
    fi
    if kill -0 "$PID" 2>/dev/null; then
      if check_owned_pid; then
        echo "readiness_failure_escalating_sigkill_owned_pid=$PID"
        kill -KILL "$PID" 2>/dev/null || true
        sleep 2
      else
        echo "REFUSE: ownership changed before SIGKILL"
      fi
    fi
  elif kill -0 "$PID" 2>/dev/null; then
    echo "REFUSE: readiness failure pid=$PID is not ownership-validated"
  fi
  rm -f "$PIDFILE"
  exit 14
fi

STARTTIME="$PID_STARTTIME"
EXE=$(readlink "/proc/$PID/exe")
CWD=$(readlink "/proc/$PID/cwd")
CMDLINE=$(tr '\0' ' ' < "/proc/$PID/cmdline")
LISTENERS=$(ss -ltnp 2>/dev/null | grep -E ':(18989|18990)[[:space:]]' || true)

printf 'PID=%s\nTOKEN=%s\nSTARTTIME=%s\nEXE=%s\nCWD=%s\nJAR=%s\nCONFIG=%s\nPBF=%s\nJAVA_VERSION=21.0.12.1+1-LTS\nSTARTED_AT=%s\n' \
  "$PID" "$TOKEN" "$STARTTIME" "$EXE" "$CWD" "$JAR" "$CONFIG" "$PBF" "$START_STAMP" > "$OWNER"

{
  echo "pid=$PID"
  echo "token=$TOKEN"
  echo "proc_starttime_ticks=$STARTTIME"
  echo "exe=$EXE"
  echo "cwd=$CWD"
  echo "cmdline=$CMDLINE"
  echo "jar_sha256=$JAR_SHA256"
  echo "pbf_sha256=$PBF_SHA256"
  echo "config_sha256=$(sha256sum "$CONFIG" | awk '{print $1}')"
  echo "started_at=$START_STAMP"
  echo "listeners="
  echo "$LISTENERS"
  echo "health=$(cat "$GH/state/startup-health.json")"
} > "$GH/state/running-fingerprint.txt"

echo "READY linux_pid=$PID"
cat "$GH/state/startup-health.json"
