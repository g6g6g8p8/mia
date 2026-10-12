#!/usr/bin/env bash
# Disposable Ubuntu userspace, clean dependencies, then offline validation.
# Usage: bash scripts/clean_ubuntu.sh <0.2.0a3-commit>
set -euo pipefail
baseline_ref="${1:?Pass the 0.2.0a3 baseline commit}"
repository="$(git rev-parse --show-toplevel)"
candidate_ref="$(git rev-parse HEAD)"
baseline_ref="$(git rev-parse --verify "${baseline_ref}^{commit}")"
validation_dir="$(mktemp -d)"
container=""
cleanup() {
  if [[ -n "$container" ]]; then docker rm -f "$container" >/dev/null; fi
  rm -rf -- "$validation_dir"
}
trap cleanup EXIT
git clone --quiet --no-hardlinks "$repository" "$validation_dir/repo"
git -C "$validation_dir/repo" checkout --quiet --detach "$candidate_ref"
container="$(docker run -d --memory=1g --cpus=2 --pids-limit=256 \
  -v "$validation_dir/repo:/src:ro" ubuntu:24.04 sleep infinity)"
docker exec "$container" bash -lc '
  set -euo pipefail
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv git ca-certificates > /tmp/apt.log
  python3 -m venv /venv
  /venv/bin/pip install --disable-pip-version-check -q -r /src/requirements.lock
  cp -a /src /build
  /venv/bin/pip install --disable-pip-version-check -q --no-deps /build
  /venv/bin/pip install --disable-pip-version-check -q pytest==8.3.4
  git config --global --add safe.directory /src
  cat /etc/os-release
  /venv/bin/python --version
'
docker network disconnect bridge "$container"
docker exec -w /tmp "$container" /venv/bin/python -m pytest -q -p no:cacheprovider /src/tests
docker exec -w /tmp "$container" /venv/bin/python /src/scripts/upgrade_smoke.py --baseline-ref "$baseline_ref"
docker exec -w /tmp "$container" /venv/bin/python /src/scripts/package_smoke.py
echo "PASS: Ubuntu clean package installation and offline checks at $candidate_ref"
