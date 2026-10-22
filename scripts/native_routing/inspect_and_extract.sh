#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/mnt/e/Project/TVLT_2026}"
JRE="$ROOT/.runtime-native/java-21.0.12.1"
GH="$ROOT/.runtime-native/graphhopper-11.1"
ARCHIVE="$JRE/download/OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz"
JAR="$GH/download/graphhopper-web-11.1.jar"

mkdir -p "$JRE/download" "$JRE/logs"
exec > >(tee "$JRE/logs/inspect-extract.log") 2>&1

echo "archive=$ARCHIVE"
echo "archive_bytes=$(stat -c%s "$ARCHIVE")"
tar -tzf "$ARCHIVE" > "$JRE/download/archive-paths.txt"
tar -tvzf "$ARCHIVE" > "$JRE/download/archive-verbose.txt"
echo "archive_entries=$(wc -l < "$JRE/download/archive-paths.txt")"

if grep -Eq '(^/|(^|/)\.\.(/|$)|^[A-Za-z]:)' "$JRE/download/archive-paths.txt"; then
  echo "REJECT: absolute, parent-relative, or drive-qualified path"
  exit 3
fi
echo "path_escape_check=OK"

TYPES=$(awk '{print substr($0,1,1)}' "$JRE/download/archive-verbose.txt" | sort | uniq -c | tr '\n' ' ')
echo "entry_types=$TYPES"
if grep -Eq '^[^dl-]' "$JRE/download/archive-verbose.txt"; then
  echo "REJECT: device, fifo, or hardlink archive entry"
  grep -E '^[^dl-]' "$JRE/download/archive-verbose.txt"
  exit 4
fi
python3 - "$ARCHIVE" <<'PY'
import posixpath, sys, tarfile
p = sys.argv[1]
tops = set()
links = 0
with tarfile.open(p, "r:gz") as t:
    members = t.getmembers()
    for m in members:
        if m.isdir() or m.isfile() or m.issym():
            pass
        else:
            raise SystemExit("REJECT: unsupported tar entry type: %s" % m.name)
        if "/" in m.name.rstrip("/"):
            tops.add(m.name.split("/", 1)[0])
        else:
            tops.add(m.name.rstrip("/"))
    top = next(iter(tops))
    symlink_paths = {m.name for m in members if m.issym()}
    for m in members:
        if not m.issym():
            continue
        links += 1
        if m.linkname.startswith("/"):
            raise SystemExit("REJECT: absolute symlink target: %s -> %s" % (m.name, m.linkname))
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(m.name), m.linkname))
        if resolved == ".." or resolved.startswith("../") or not resolved.startswith(top + "/"):
            raise SystemExit("REJECT: escaping symlink target: %s -> %s" % (m.name, m.linkname))
        parent = posixpath.dirname(m.name)
        parts = parent.split("/")
        for i in range(1, len(parts) + 1):
            if "/".join(parts[:i]) in symlink_paths:
                raise SystemExit("REJECT: symlink ancestor: %s" % m.name)
    print("top_level=%s" % top)
    print("symlink_count=%d" % links)
    print("symlink_target_check=OK")
PY
echo "special_entry_check=OK"

TOPS=$(cut -d/ -f1 "$JRE/download/archive-paths.txt" | sort -u)
echo "top_level_entries=$(echo "$TOPS" | tr '\n' ' ')"
if [ "$(echo "$TOPS" | wc -l)" -ne 1 ]; then
  echo "REJECT: expected exactly one top-level entry"
  exit 5
fi
TOP="$TOPS"
if [ -z "$TOP" ] || [ "$TOP" = "." ]; then
  echo "REJECT: empty top-level entry"
  exit 5
fi

if grep -Eiq '(^|/)(install|setup|uninstall)[^/]*$|\.(sh|bat|cmd|ps1)$' "$JRE/download/archive-paths.txt"; then
  echo "REJECT: install/script entry found"
  grep -Ei '(^|/)(install|setup|uninstall)[^/]*$|\.(sh|bat|cmd|ps1)$' "$JRE/download/archive-paths.txt"
  exit 6
fi
echo "install_script_check=OK"

if [ -n "$(find "$JRE/root" -mindepth 1 -print -quit)" ]; then
  echo "REJECT: extraction target not empty"
  exit 7
fi

tar -xzf "$ARCHIVE" -C "$JRE/root" --no-same-owner --no-same-permissions
JAVA="$JRE/root/$TOP/bin/java"
if [ ! -x "$JAVA" ]; then
  echo "REJECT: java executable missing or not executable"
  exit 8
fi
JAVA_REAL=$(readlink -f "$JAVA")
ROOT_REAL=$(readlink -f "$JRE/root")
case "$JAVA_REAL" in
  "$ROOT_REAL"/*) echo "java_within_own_tree=OK" ;;
  *) echo "REJECT: java resolves outside own tree"; exit 8 ;;
esac
echo "java_path=$JAVA"
echo "java_realpath=$JAVA_REAL"
echo "java_sha256=$(sha256sum "$JAVA_REAL" | awk '{print $1}')"
echo "java_version:"
HOME="$JRE/home" TMPDIR="$JRE/tmp" "$JAVA" -version 2>&1

echo "jar=$JAR"
echo "jar_bytes=$(stat -c%s "$JAR")"
python3 - "$JAR" <<'PY'
import sys, zipfile
p = sys.argv[1]
with zipfile.ZipFile(p) as z:
    names = z.namelist()
    print("jar_entries=%d" % len(names))
    print("jar_pom_properties=%s" % any(n.endswith("pom.properties") for n in names))
    mf = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    for line in mf.splitlines():
        if line.lower().startswith(("implementation-version", "implementation-title", "main-class", "build-jdk")):
            print("manifest_" + line)
    for n in names:
        if n.endswith("pom.properties"):
            print("pom=" + n)
            print(z.read(n).decode("utf-8", "replace").strip())
            break
PY
