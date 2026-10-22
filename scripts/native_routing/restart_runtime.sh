#!/usr/bin/env bash
set -euo pipefail

DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
bash "$DIR/stop_runtime.sh"
bash "$DIR/start_runtime.sh"
