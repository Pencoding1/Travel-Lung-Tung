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

echo "checked_at=$(date -Ins)"

if [ ! -f "$PIDFILE" ] || [ ! -f "$OWNER" ]; then
  echo "status=stopped"
  exit 0
fi

set -a
. "$OWNER"
set +a

if ! kill -0 "$PID" 2>/dev/null; then
  echo "status=stopped_stale_pidfile pid=$PID"
  exit 0
fi

NOW_STARTTIME=$(awk '{print $22}' "/proc/$PID/stat" 2>/dev/null || true)
NOW_EXE=$(readlink "/proc/$PID/exe" 2>/dev/null || true)
NOW_CWD=$(readlink "/proc/$PID/cwd" 2>/dev/null || true)
NOW_CMDLINE=$(tr '\0' ' ' < "/proc/$PID/cmdline" 2>/dev/null || true)

echo "pid=$PID"
echo "token=$TOKEN"
echo "exe=$NOW_EXE"
echo "cwd=$NOW_CWD"
echo "cmdline=$NOW_CMDLINE"
echo "proc_starttime_ticks=$NOW_STARTTIME"

if [ "$NOW_STARTTIME" != "$STARTTIME" ]; then
  echo "status=foreign_mismatch reason=starttime"
  exit 3
fi
if [ "$NOW_EXE" != "$JAVA_REAL" ]; then
  echo "status=foreign_mismatch reason=exe"
  exit 3
fi
if [ "$NOW_CWD" != "$WORK" ]; then
  echo "status=foreign_mismatch reason=cwd"
  exit 3
fi
case "$NOW_CMDLINE" in
  *"$JAR"*"$CONFIG"*) ;;
  *) echo "status=foreign_mismatch reason=cmdline"; exit 3 ;;
esac

LISTENERS=$(ss -ltnp 2>/dev/null | grep -E ':(18989|18990)[[:space:]]' || true)
echo "listeners:"
echo "$LISTENERS"
OWN_APP=$(echo "$LISTENERS" | grep ':18989 ' || true)
OWN_ADMIN=$(echo "$LISTENERS" | grep ':18990 ' || true)
if ! echo "$OWN_APP" | grep -q "pid=$PID"; then
  echo "status=ownership_mismatch reason=app_listener"
  exit 3
fi
if ! echo "$OWN_ADMIN" | grep -q "pid=$PID"; then
  echo "status=ownership_mismatch reason=admin_listener"
  exit 3
fi

CODE=$(curl -sS -o "$GH/state/status-health.json" -w '%{http_code}' --max-time 3 http://127.0.0.1:18989/health 2>/dev/null || true)
echo "health_http=$CODE"
echo "health=$(cat "$GH/state/status-health.json" 2>/dev/null || true)"
if [ "$CODE" = "200" ]; then
  echo "status=running_owned_healthy"
else
  echo "status=running_owned_unhealthy"
  exit 4
fi
