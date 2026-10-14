#!/bin/bash
# Developer build pipeline. Participant installations do not run this script.
set -euo pipefail

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
  task_prepared="$task_output/prepared"
  python3 "$task_repo/scripts/prepare_macos_artifacts.py" --output "$task_prepared" --cache "$task_cache" --platform macos --architecture "$task_arch"
fi
python3 "$task_repo/scripts/prepare_macos_artifacts.py" --verify-prepared "$task_prepared" --cache "$task_cache" --platform macos --architecture "$task_arch"
if [ -n "$task_remote" ]; then
  python3 "$task_repo/scripts/prepare_macos_artifacts.py" --verify-prepared "$task_remote/payload" --cache "$task_cache" --platform linux --architecture x86_64
fi
swift test --package-path "$task_repo/macos/Mia" --disable-automatic-resolution
swift build --package-path "$task_repo/macos/Mia" -c release --disable-automatic-resolution
task_bin=$(swift build --package-path "$task_repo/macos/Mia" -c release --show-bin-path --disable-automatic-resolution)
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
python3 "$task_repo/scripts/package_macos.py" "${task_args[@]}"

# Perform an actual offline backend install/start/health/stop on this Mac using
# synthetic empty data. No LaunchAgent is activated by the build pipeline.
python3 - "$task_repo" "$task_output/Mia.app" <<'PY'
from pathlib import Path
import json, socket, sys, tempfile, urllib.request
sys.path.insert(0, sys.argv[1])
from mia.operations import Manager
resources = Path(sys.argv[2]) / 'Contents/Resources'
with tempfile.TemporaryDirectory(prefix='mia-mac-build-smoke-') as stage:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
    manager = Manager(Path(stage) / 'installation')
    runtime = resources / 'runtime/bin/python3'
    import subprocess
    subprocess.run([str(runtime), '-I', str(resources/'source/mia/operations.py'), '--root', str(manager.root), 'install', '--source', str(resources/'source'), '--wheelhouse', str(resources/'wheelhouse'), '--offline', '--port', str(port)], check=True)
    try:
        manager.start()
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status', timeout=5) as response:
            status = json.load(response)
        assert status['configured'] is False
        assert status['version'] == json.loads((resources/'build-report.json').read_text())['app_version']
    finally:
        if manager.root.exists(): manager.stop()
print('PASS: actual native-Mac offline backend install/health/empty data; graphical/OS lifecycle acceptance remains separate')
PY

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
  python3 "$task_repo/scripts/prepare_macos_artifacts.py" --sign-app "$task_output/Mia.app" --sign-identity "$task_identity"
fi
mkdir "$task_output/dmg-root"
ditto "$task_output/Mia.app" "$task_output/dmg-root/Mia.app"
ln -s /Applications "$task_output/dmg-root/Applications"
hdiutil create -quiet -volname Mia -srcfolder "$task_output/dmg-root" -format UDZO -o "$task_output/$task_name.dmg"
if [ "$task_unsigned" = false ]; then
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
python3 - "$task_output/$task_name.dmg" "$task_unsigned" <<'PY'
from pathlib import Path
import hashlib,json,sys
p=Path(sys.argv[1])
with p.open('rb') as f: sha=hashlib.file_digest(f,'sha256').hexdigest()
Path(str(p)+'.sha256').write_text(sha+'  '+p.name+'\n')
Path(str(p)+'.verification.json').write_text(json.dumps({'artifact':p.name,'sha256':sha,'signed':sys.argv[2]=='false','notarized':sys.argv[2]=='false','native_backend_smoke_passed':True,'clean_mac_ui_acceptance':False,'consumer_distribution_ready':False},indent=2))
PY
echo "Built: $task_output/$task_name.dmg"
