#!/usr/bin/env bash
set -euo pipefail

smoke_dir="$(mktemp -d)"
smoke_port="${MIA_SMOKE_PORT:-18123}"

MIA_DATA_DIR="$smoke_dir" .venv/bin/uvicorn mia.app:app \
  --host 127.0.0.1 --port "$smoke_port" >"$smoke_dir/server.log" 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
  if curl --fail --silent "http://127.0.0.1:$smoke_port/health" >"$smoke_dir/health.json"; then
    break
  fi
  sleep 0.2
done

curl --fail --silent "http://127.0.0.1:$smoke_port/" | grep -q '<title>Mia</title>'
curl --fail --silent --output /dev/null "http://127.0.0.1:$smoke_port/assets/mia-icon.svg"
grep -q '"ok":true' "$smoke_dir/health.json"

echo "HTTP smoke test passed"
