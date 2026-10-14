#!/bin/bash
# Developer build pipeline. Participant installations do not run this script.
set -Eeuo pipefail

task_stage='argument and host checks'
build_failed() {
  task_failure_status=$?
  trap - ERR
  printf 'Mia Mac build failed during %s (exit %s).\n' "$task_stage" "$task_failure_status" >&2
  # Report packaging capacity only, never expand commands containing signing
  # identities or Keychain profile names. The original failure remains fatal.
  if [ -n "${task_output:-}" ] && [ -d "$task_output" ]; then
    df -h "$task_output" >&2 || true
    if [ -d "$task_output/Mia.app" ]; then du -sh "$task_output/Mia.app" >&2 || true; fi
    if [ -d "$task_output/dmg-root" ]; then du -sh "$task_output/dmg-root" >&2 || true; fi
  fi
  exit "$task_failure_status"
}
trap build_failed ERR

usage() {
  cat <<'HELP'
Build the Mia native Mac app with verified bundled runtimes/offline wheels.

  scripts/build_macos_app.sh --preflight
  scripts/build_macos_app.sh --output /new/artifact-dir --unsigned [options]
  scripts/build_macos_app.sh --output /new/artifact-dir \
    --sign-identity 'Developer ID Application: …' --notary-profile PROFILE [options]

Options:
  --prepared DIR          Previously prepared native artifacts (verified again).
  --remote-artifact DIR   Verified Ubuntu 24.04 amd64 companion to include.
  --local-only            Internal build without server-install artifact.
  --release-channel FILE Reviewed public signed-feed/appcast configuration.
  --cache DIR             Download cache (every cached runtime hash is checked).
  --unsigned              Internal development artifact; not a beta download.
  --preflight             Read-only host/tool checks; does not download or build.
  --help                  This help; works without a Mac.

Requires native macOS, Xcode/Swift, Python >=3.12 for build tooling, and zstd.
Signing uses an existing Developer ID certificate in the developer's Keychain.
Notarization uses an existing notarytool Keychain profile; no passwords/tokens
are accepted as arguments or copied into artifacts. There is no Gatekeeper
bypass. Unsigned CI artifacts are separate from signed/notarized delivery.
HELP
}

task_output=''
task_prepared=''
task_remote=''
task_channel=''
task_cache=''
task_identity=''
task_notary=''
task_unsigned=false
task_preflight=false
task_local_only=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --preflight) task_preflight=true; shift ;;
    --unsigned) task_unsigned=true; shift ;;
    --local-only) task_local_only=true; shift ;;
    --output|--prepared|--remote-artifact|--release-channel|--cache|--sign-identity|--notary-profile)
      [ "$#" -ge 2 ] || { echo "Missing value: $1" >&2; exit 2; }
      case "$1" in
        --output) task_output=$2 ;;
        --prepared) task_prepared=$2 ;;
        --remote-artifact) task_remote=$2 ;;
        --release-channel) task_channel=$2 ;;
        --cache) task_cache=$2 ;;
        --sign-identity) task_identity=$2 ;;
        --notary-profile) task_notary=$2 ;;
      esac
      shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

[ "$(uname -s)" = Darwin ] || { echo "Native Mac build required; cloud Linux cannot validate a Mac artifact." >&2; exit 1; }
task_arch=$(uname -m)
case "$task_arch" in arm64|x86_64) ;; *) echo "Unsupported architecture." >&2; exit 1 ;; esac
for task_tool in python3 swift xcrun hdiutil codesign security zstd; do
  command -v "$task_tool" >/dev/null || { echo "Missing build tool: $task_tool" >&2; exit 1; }
done
python3 -c 'import sys; assert sys.version_info >= (3,12), "Build tooling requires Python 3.12+"'
xcrun --find swift >/dev/null
if [ "$task_preflight" = true ]; then
  echo "Preflight: native macOS $task_arch; required build tools present. No artifact built."
  exit 0
fi
[ -n "$task_output" ] || { usage >&2; exit 2; }
[ ! -e "$task_output" ] && [ ! -L "$task_output" ] || { echo "Output must be a new directory." >&2; exit 1; }
if [ "$task_unsigned" = true ]; then
  [ -z "$task_identity" ] && [ -z "$task_notary" ] || { echo "Unsigned mode cannot use signing credentials." >&2; exit 2; }
else
  case "$task_identity" in 'Developer ID Application: '*) ;; *) echo "Developer ID identity required; use --unsigned for internal builds." >&2; exit 2 ;; esac
  [ -n "$task_notary" ] || { echo "Existing notarytool Keychain profile required." >&2; exit 2; }
fi
if [ "$task_local_only" = false ] && [ -z "$task_remote" ]; then
  echo "Include the verified server companion, or explicitly choose --local-only for an internal build." >&2
  exit 2
fi

task_repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$task_output"
task_output=$(CDPATH= cd -- "$task_output" && pwd)
if [ -z "$task_cache" ]; then task_cache="$task_output/download-cache"; fi
if [ -z "$task_prepared" ]; then
  task_stage='preparing pinned Mac runtime and wheels'
  task_prepared="$task_output/prepared"
  python3 "$task_repo/scripts/prepare_macos_artifacts.py" --output "$task_prepared" --cache "$task_cache" --platform macos --architecture "$task_arch"
fi
task_stage='verifying pinned runtime provenance'
python3 "$task_repo/scripts/prepare_macos_artifacts.py" --verify-prepared "$task_prepared" --cache "$task_cache" --platform macos --architecture "$task_arch"
if [ -n "$task_remote" ]; then
  python3 "$task_repo/scripts/prepare_macos_artifacts.py" --verify-prepared "$task_remote/payload" --cache "$task_cache" --platform linux --architecture x86_64
fi
task_stage='running native Swift tests'
swift test --package-path "$task_repo/macos/Mia" --force-resolved-versions
task_stage='compiling native release executable'
swift build --package-path "$task_repo/macos/Mia" -c release --force-resolved-versions
task_bin=$(swift build --package-path "$task_repo/macos/Mia" -c release --show-bin-path --force-resolved-versions)
task_framework=$(python3 - "$task_repo/macos/Mia/.build/artifacts" <<'PY'
from pathlib import Path
import sys
paths = [p for p in Path(sys.argv[1]).rglob('Sparkle.framework') if 'macos-arm64_x86_64' in str(p)]
if len(paths) != 1:
    raise SystemExit('Exactly one verified Sparkle macOS framework must be resolved by SwiftPM')
print(paths[0])
PY
)
task_args=(--output "$task_output/Mia.app" --runtime "$task_prepared/runtime" --runtime-manifest "$task_prepared/runtime-manifest.json" --wheelhouse "$task_prepared/wheelhouse" --wheelhouse-manifest "$task_prepared/wheelhouse-manifest.json" --native-binary "$task_bin/Mia" --sparkle-framework "$task_framework")
if [ -n "$task_remote" ]; then task_args+=(--remote-artifact "$task_remote"); fi
if [ -n "$task_channel" ]; then task_args+=(--release-channel "$task_channel"); fi
task_stage='assembling verified native app bundle'
python3 "$task_repo/scripts/package_macos.py" "${task_args[@]}"

# Exercise the final runtime after any Developer ID signing. Native extensions
# installed from verified wheels must load under the actual hardened runtime.
# Synthetic empty data only; no LaunchAgent is activated by the build pipeline.
test_backend_runtime() {
  task_stage='testing final runtime and private first-owner setup'
  python3 - "$task_repo" "$task_output/Mia.app" <<'PY'
from pathlib import Path
import json, secrets, socket, sys, tempfile, urllib.error, urllib.request
sys.path.insert(0, sys.argv[1])
from mia.operations import Manager
from scripts.package_macos import inventory
resources = Path(sys.argv[2]) / 'Contents/Resources'
runtime_before = inventory(resources / 'runtime')
with tempfile.TemporaryDirectory(prefix='mia-mac-build-smoke-') as stage:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
    manager = Manager(Path(stage) / 'installation')
    runtime = resources / 'runtime/bin/python3'
    import subprocess
    subprocess.run([str(runtime), '-I', '-B', str(resources/'source/mia/operations.py'), '--root', str(manager.root), 'install', '--source', str(resources/'source'), '--wheelhouse', str(resources/'wheelhouse'), '--offline', '--port', str(port), '--private-bootstrap'], check=True)
    try:
        manager.start()
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status', timeout=5) as response:
            status = json.load(response)
        assert status['configured'] is False
        assert status['version'] == json.loads((resources/'build-report.json').read_text())['app_version']
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/installation', timeout=5) as response:
            installation = json.load(response)
        assert installation['bootstrap_protected'] is True
        # A real native install must remain unclaimed until the app supplies its
        # private capability. Exercise both paths with disposable synthetic data;
        # the token/password never appear in command arguments or build output.
        payload = json.dumps({'name': 'Native build smoke', 'password': secrets.token_urlsafe(24)}).encode()
        setup_url = f'http://127.0.0.1:{port}/api/setup'
        request = urllib.request.Request(setup_url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            assert error.code == 401, 'Unclaimed native installation must require its private bootstrap capability'
        else:
            raise AssertionError('First-owner creation was permitted without the private bootstrap capability')
        token = (manager.root/'bootstrap-token').read_text().strip()
        request = urllib.request.Request(setup_url, data=payload, headers={'Content-Type': 'application/json', 'Cookie': 'mia_bootstrap=' + token}, method='POST')
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 201
            assert 'mia_bootstrap=""' in response.headers.get('Set-Cookie', '') or any('mia_bootstrap=""' in value for value in response.headers.get_all('Set-Cookie', []))
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status', timeout=5) as response:
            assert json.load(response)['configured'] is True
    finally:
        if manager.root.exists(): manager.stop()
assert inventory(resources / 'runtime') == runtime_before, 'Bundled runtime mutated during native offline smoke'
print('PASS: actual native-Mac offline backend install/health/private first-owner setup; graphical/OS lifecycle acceptance remains separate')
PY
}

task_version=$(python3 - "$task_repo/pyproject.toml" <<'PY'
import sys,tomllib
print(tomllib.load(open(sys.argv[1],'rb'))['project']['version'])
PY
)
if [ "$task_unsigned" = true ]; then
  task_name="Mia-Development-$task_version-$task_arch"
  echo "Unsigned internal artifact: signing, notarization and clean-Mac UI acceptance remain required."
else
  task_name="Mia-$task_version-$task_arch"
  task_stage='signing native app bundle'
  python3 "$task_repo/scripts/prepare_macos_artifacts.py" --sign-app "$task_output/Mia.app" --sign-identity "$task_identity"
fi
test_backend_runtime
task_stage='staging disk-image contents'
echo 'Mia Mac build: staging disk-image contents.'
mkdir "$task_output/dmg-root"
ditto "$task_output/Mia.app" "$task_output/dmg-root/Mia.app"
ln -s /Applications "$task_output/dmg-root/Applications"
task_stage='creating compressed disk image'
echo 'Mia Mac build: creating compressed disk image.'
hdiutil create -volname Mia -srcfolder "$task_output/dmg-root" -format UDZO -o "$task_output/$task_name.dmg"
if [ "$task_unsigned" = false ]; then
  task_stage='signing and notarizing disk image'
  codesign --force --timestamp --sign "$task_identity" "$task_output/$task_name.dmg"
  xcrun notarytool submit "$task_output/$task_name.dmg" --keychain-profile "$task_notary" --wait --output-format json > "$task_output/notarization-result.json"
  python3 - "$task_output/notarization-result.json" <<'PY'
import json,sys
if json.load(open(sys.argv[1])).get('status') != 'Accepted':
    raise SystemExit('Notarization did not accept the artifact; do not distribute')
PY
  xcrun stapler staple "$task_output/$task_name.dmg"
  xcrun stapler validate "$task_output/$task_name.dmg"
  spctl --assess --type open --context context:primary-signature --verbose "$task_output/$task_name.dmg"
fi
task_stage='verifying final disk-image integrity'
hdiutil verify "$task_output/$task_name.dmg"
task_stage='writing artifact digest and verification receipt'
python3 - "$task_output/$task_name.dmg" "$task_unsigned" "$task_repo" "$task_output/Mia.app" "$task_output/dmg-root/Mia.app" <<'PY'
from pathlib import Path
import hashlib,json,sys
sys.path.insert(0,sys.argv[3])
from scripts.package_macos import inventory
p=Path(sys.argv[1])
with p.open('rb') as f: sha=hashlib.file_digest(f,'sha256').hexdigest()
app_files=inventory(Path(sys.argv[4]))
assert app_files==inventory(Path(sys.argv[5])), 'Staged app must match the final tested app bytes'
app_digest=hashlib.sha256(json.dumps(app_files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
Path(str(p)+'.sha256').write_text(sha+'  '+p.name+'\n')
Path(str(p)+'.verification.json').write_text(json.dumps({'artifact':p.name,'sha256':sha,'disk_image_integrity_verified':True,'signed':sys.argv[2]=='false','notarized':sys.argv[2]=='false','native_backend_smoke_passed':True,'native_backend_smoke_scope':'final app runtime after code signing' if sys.argv[2]=='false' else 'unsigned development app runtime','app_files':app_files,'app_inventory_sha256':app_digest,'clean_mac_ui_acceptance':False,'consumer_distribution_ready':False},indent=2))
PY
echo "Built: $task_output/$task_name.dmg"
