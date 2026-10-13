"""Release checks must detect omitted notices and accidental private artifacts."""
import importlib.util
import json
from pathlib import Path
import shutil
import tarfile
import zipfile

import pytest


spec = importlib.util.spec_from_file_location(
    "mia_distribution_check", Path(__file__).resolve().parents[1] / "scripts/check_distribution.py"
)
distribution = importlib.util.module_from_spec(spec)
spec.loader.exec_module(distribution)


def make_wheel(tmp_path, extra=None, *, notice=b"Original copyright and license"):
    target = tmp_path / "mia_test-1.0-py3-none-any.whl"
    with zipfile.ZipFile(target, "w") as wheel:
        wheel.writestr("mia_test-1.0.dist-info/licenses/THIRD_PARTY_LICENSES/dependency--LICENSE", notice)
        for path in ["mia/static/index.html", "mia/static/assets/app.js", "mia/static/assets/app.css"]:
            wheel.writestr(path, "synthetic asset")
        for path, content in (extra or {}).items():
            wheel.writestr(path, content)
    return target


def test_current_lock_keeps_original_notice_inventory():
    expected = distribution.inventory_files()
    assert "THIRD_PARTY_NOTICES.md" in expected
    assert "THIRD_PARTY_LICENSES/inventory.json" in expected
    assert "THIRD_PARTY_LICENSES/rust-inventory.json" in expected


@pytest.mark.parametrize("failure", ["runtime_version", "notice_bytes", "unknown_file"])
def test_rust_supplement_rejects_drift_and_unreviewed_files(tmp_path, failure):
    shutil.copytree(distribution.ROOT / "THIRD_PARTY_LICENSES", tmp_path / "THIRD_PARTY_LICENSES")
    for name in ["THIRD_PARTY_NOTICES.md", "requirements.lock"]:
        shutil.copyfile(distribution.ROOT / name, tmp_path / name)
    path = tmp_path / "THIRD_PARTY_LICENSES/rust-inventory.json"
    inventory = json.loads(path.read_text())
    if failure == "runtime_version":
        inventory["source_archives"][0]["version"] = "999.0"
        path.write_text(json.dumps(inventory))
    elif failure == "notice_bytes":
        (tmp_path / inventory["packages"][0]["files"][0]["path"]).write_bytes(b"Copyright removed")
    else:
        (tmp_path / "THIRD_PARTY_LICENSES/unreviewed.txt").write_bytes(b"Unreviewed")
    with pytest.raises(ValueError):
        distribution.inventory_files(tmp_path)


def test_archive_requires_original_license_bytes(tmp_path):
    expected = {"THIRD_PARTY_LICENSES/dependency--LICENSE": b"Original copyright and license"}
    distribution.check_archive(make_wheel(tmp_path), expected)
    with pytest.raises(ValueError, match="Missing or altered notice"):
        distribution.check_archive(make_wheel(tmp_path, notice=b"Copyright removed"), expected)


def test_archive_cannot_omit_notice(tmp_path):
    expected = {"THIRD_PARTY_LICENSES/missing--LICENSE": b"Required notice"}
    with pytest.raises(ValueError, match="Missing or altered notice"):
        distribution.check_archive(make_wheel(tmp_path), expected)


@pytest.mark.parametrize("name", ["data/owner.db", ".env", ".aws/credentials", "../outside", "/absolute"])
def test_archive_rejects_local_private_or_unsafe_paths(tmp_path, name):
    archive = make_wheel(tmp_path, {name: b"synthetic"})
    with pytest.raises(ValueError):
        distribution.archive_files(archive)


def test_archive_rejects_selected_credential_without_printing_it(tmp_path):
    synthetic_key = b"-----BEGIN " + b"PRIVATE KEY-----"
    archive = make_wheel(tmp_path, {"mia/accidental.txt": synthetic_key})
    with pytest.raises(ValueError, match="credential pattern") as caught:
        distribution.archive_files(archive)
    assert synthetic_key.decode() not in str(caught.value)


def test_sdist_never_follows_links(tmp_path):
    archive = tmp_path / "mia_test-1.0.tar.gz"
    with tarfile.open(archive, "w:gz") as sdist:
        link = tarfile.TarInfo("mia_test-1.0/linked-license")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        sdist.addfile(link)
    with pytest.raises(ValueError, match="Nonregular member"):
        distribution.archive_files(archive)
