#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/mnt/e/Project/TVLT_2026}"
GH="$ROOT/.runtime-native/graphhopper-11.1"
JRE="$ROOT/.runtime-native/java-21.0.12.1"

JAR_URL="https://repo.maven.apache.org/maven2/com/graphhopper/graphhopper-web/11.1/graphhopper-web-11.1.jar"
JAR_BASE="https://repo.maven.apache.org/maven2/com/graphhopper/graphhopper-web/11.1"
JRE_BASE="https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz"
JRE_SHA_URL="$JRE_BASE.sha256.txt"
JRE_JSON_URL="$JRE_BASE.json"
JRE_SIG_URL="$JRE_BASE.sig"
CONFIG_URL="https://raw.githubusercontent.com/graphhopper/graphhopper/11.1/config-example.yml"

mkdir -p "$GH/download" "$GH/app" "$GH/config" "$GH/work" "$GH/logs" "$GH/state" "$GH/home" "$GH/tmp" "$GH/graph-cache"
mkdir -p "$JRE/download" "$JRE/root" "$JRE/home" "$JRE/tmp"
exec > >(tee "$GH/logs/fetch-artifacts.log") 2>&1

AVAIL=$(df -B1 --output=avail "$ROOT" | tail -1 | tr -d ' ')
echo "free_bytes=$AVAIL"
if [ "$AVAIL" -lt 2147483648 ]; then
  echo "ERROR: free space below 2GiB" >&2
  exit 2
fi

cd "$GH/download"
echo "jar_url=$JAR_URL"
curl -fL --max-time 900 --retry 2 --retry-delay 2 --max-filesize 268435456 \
  -o graphhopper-web-11.1.jar "$JAR_URL"
echo "jar_bytes=$(stat -c%s graphhopper-web-11.1.jar)"

for EXT in sha1 md5 sha256 sha512; do
  CODE=$(curl -sS -L --max-time 60 --retry 2 -o "graphhopper-web-11.1.jar.$EXT" \
    -w '%{http_code}' "$JAR_BASE/graphhopper-web-11.1.jar.$EXT")
  echo "jar_checksum_${EXT}_http=$CODE bytes=$(stat -c%s "graphhopper-web-11.1.jar.$EXT")"
done

CODE=$(curl -sS -L --max-time 120 --retry 2 -o config-example-11.1.yml \
  -w '%{http_code}' "$CONFIG_URL")
echo "config_example_http=$CODE bytes=$(stat -c%s config-example-11.1.yml)"

cd "$JRE/download"
echo "jre_url=$JRE_BASE"
curl -fL --max-time 900 --retry 2 --retry-delay 2 --max-filesize 268435456 \
  -o OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz "$JRE_BASE"
echo "jre_bytes=$(stat -c%s OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz)"

for PAIR in "sha256.txt|$JRE_SHA_URL" "metadata.json|$JRE_JSON_URL" "signature.sig|$JRE_SIG_URL"; do
  OUT="${PAIR%%|*}"
  URL="${PAIR#*|}"
  CODE=$(curl -sS -L --max-time 60 --retry 2 -o "$OUT" -w '%{http_code}' "$URL")
  echo "jre_${OUT}_http=$CODE bytes=$(stat -c%s "$OUT")"
done

echo "jre_vendor_checksum_file:"
cat sha256.txt
echo "jre_vendor_checksum_check:"
sha256sum -c sha256.txt
echo "jre_actual_sha256=$(sha256sum OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz | awk '{print $1}')"

cd "$GH/download"
echo "jar_actual_sha256=$(sha256sum graphhopper-web-11.1.jar | awk '{print $1}')"
echo "jar_actual_sha1=$(sha1sum graphhopper-web-11.1.jar | awk '{print $1}')"
echo "jar_actual_sha512=$(sha512sum graphhopper-web-11.1.jar | awk '{print $1}')"
