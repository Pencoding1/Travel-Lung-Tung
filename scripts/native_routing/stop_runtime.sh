#!/usr/bin/env bash
set -euo pipefail

ROOT="${TVLT_ROOT:-/mnt/e/Project/TVLT_2026}"
GH="$ROOT/.runtime-native/graphhopper-11.1"
JRE="$ROOT/.runtime-native/java-21.0.12.1"
JAVA_REAL=$(readlink -f "$JRE/root/jdk-21.0.12.1+1-jre/bin/java")
JAR="$GH/download/graphhopper-web-11.1.jar"
CONFIG="$GH/config/config.yml"
WORK="$GH/work"
PIDFILE="$GH/state/graphhopper.pid"
OWNER="$GH/state/owner.env"

echo "stop_requested_at=$(date -Ins)"

if [ ! -f "$PIDFILE" ] || [ ! -f "$OWNER" ]; then
  echo "status=already_stopped"
  exit 0
fi

set -a
. "$OWNER"
set +a

check_owned() {
  kill -0 "$PID" 2>/dev/null || return 1
  [ "$(awk '{print $22}' "/proc/$PID/stat" 2>/dev/null || true)" = "$STARTTIME" ] || return 1
  [ "$(readlink "/proc/$PID/exe" 2>/dev/null || true)" = "$JAVA_REAL" ] || return 1
  [ "$(readlink "/proc/$PID/cwd" 2>/dev/null || true)" = "$WORK" ] || return 1
  CMD=$(tr '\0' ' ' < "/proc/$PID/cmdline" 2>/dev/null || true)
  case "$CMD" in
    *"$JAR"*"$CONFIG"*) return 0 ;;
    *) return 1 ;;
  esac
}

if ! check_owned; then
  if kill -0 "$PID" 2>/dev/null; then
    echo "REFUSE: pid=$PID is not the owned runtime"
    exit 3
  fi
  echo "status=already_stopped_stale_pidfile pid=$PID"
  rm -f "$PIDFILE"
  exit 0
fi

echo "validated_owned_pid=$PID"
if ! check_owned; then
  echo "REFUSE: ownership changed during recheck"
  exit 3
fi

kill -TERM "$PID"
for _ in $(seq 1 30); do
  if ! kill -0 "$PID" 2>/dev/null; then
    break
  fi
  sleep 1
done

if kill -0 "$PID" 2>/dev/null; then
  if check_owned; then
    echo "escalating_to_sigkill_owned_pid=$PID"
    kill -KILL "$PID"
    sleep 2
  else
    echo "REFUSE: ownership changed before escalation"
    exit 3
  fi
fi

if kill -0 "$PID" 2>/dev/null; then
  echo "status=stop_failed pid=$PID"
  exit 4
fi

rm -f "$PIDFILE"
printf 'STOPPED_PID=%s\nSTOPPED_AT=%s\n' "$PID" "$(date -Ins)" > "$GH/state/stopped.env"
echo "status=stopped_owned pid=$PID"
