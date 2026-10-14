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


def make_wheel(tmp_path, extra=None, *, notice=b"Original copyright and license", own_notice=None):
    target = tmp_path / "mia_test-1.0-py3-none-any.whl"
    with zipfile.ZipFile(target, "w") as wheel:
        wheel.writestr("mia_test-1.0.dist-info/licenses/THIRD_PARTY_LICENSES/dependency--LICENSE", notice)
        own_license = (distribution.ROOT / "LICENSE").read_text()
        wheel.writestr("mia_test-1.0.dist-info/licenses/LICENSE", own_license)
        wheel.writestr("mia_test-1.0.dist-info/licenses/NOTICE", own_notice if own_notice is not None else (distribution.ROOT / "NOTICE").read_bytes())
        wheel.writestr("mia_test-1.0.dist-info/METADATA",
                       "Metadata-Version: 2.1\nName: mia-test\nVersion: 1.0\n"
                       + "Classifier: " + distribution.APACHE_CLASSIFIER + "\n"
                       + "License-File: LICENSE\nLicense-File: NOTICE\n"
                       + "License: " + own_license.replace("\n", "\n        ") + "\n\n")
        for path in ["mia/static/index.html", "mia/static/assets/app.js", "mia/static/assets/app.css"]:
            wheel.writestr(path, "synthetic asset")
        for path, content in (extra or {}).items():
            wheel.writestr(path, content)
    return target


def test_current_lock_keeps_original_notice_inventory():
    expected = distribution.inventory_files()
    assert "THIRD_PARTY_NOTICES.md" in expected
    assert "LICENSE" in expected and "NOTICE" in expected
    assert "THIRD_PARTY_LICENSES/inventory.json" in expected
    assert "THIRD_PARTY_LICENSES/rust-inventory.json" in expected


def test_native_dependency_same_version_cannot_change_reviewed_revision(tmp_path):
    shutil.copytree(distribution.ROOT / "THIRD_PARTY_LICENSES", tmp_path / "THIRD_PARTY_LICENSES")
    for name in ["THIRD_PARTY_NOTICES.md", "requirements.lock", "pyproject.toml", "LICENSE", "NOTICE"]:
        shutil.copyfile(distribution.ROOT / name, tmp_path / name)
    native = tmp_path / "macos/Mia"
    native.mkdir(parents=True)
    for name in ("Package.swift", "Package.resolved"):
        shutil.copyfile(distribution.ROOT / "macos/Mia" / name, native / name)
    distribution.inventory_files(tmp_path)
    path = native / "Package.resolved"
    pins = json.loads(path.read_text())
    pins["pins"][0]["state"]["revision"] = "0" * 40
    path.write_text(json.dumps(pins))
    with pytest.raises(ValueError, match="resolved dependency"):
        distribution.inventory_files(tmp_path)


@pytest.mark.parametrize("failure", ["runtime_version", "notice_bytes", "unknown_file"])
def test_rust_supplement_rejects_drift_and_unreviewed_files(tmp_path, failure):
    shutil.copytree(distribution.ROOT / "THIRD_PARTY_LICENSES", tmp_path / "THIRD_PARTY_LICENSES")
    for name in ["THIRD_PARTY_NOTICES.md", "requirements.lock", "pyproject.toml", "LICENSE", "NOTICE"]:
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


@pytest.mark.parametrize("failure", ["missing_license", "modified_grant", "wrong_metadata"])
def test_project_grant_rejects_missing_modified_or_mislabelled_license(tmp_path, failure):
    for name in ["pyproject.toml", "LICENSE", "NOTICE"]:
        shutil.copyfile(distribution.ROOT / name, tmp_path / name)
    if failure == "missing_license":
        (tmp_path / "LICENSE").unlink()
    elif failure == "modified_grant":
        (tmp_path / "LICENSE").write_bytes(b"An incomplete license grant")
    else:
        manifest = tmp_path / "pyproject.toml"
        manifest.write_text(manifest.read_text().replace("Apache Software License", "MIT License"))
    with pytest.raises((OSError, ValueError)):
        distribution.project_license_files(tmp_path)


def test_archive_rejects_incorrect_project_license_metadata(tmp_path):
    archive = make_wheel(tmp_path)
    files = distribution.archive_files(archive)
    metadata_path = "mia_test-1.0.dist-info/METADATA"
    files[metadata_path] = files[metadata_path].replace(distribution.APACHE_CLASSIFIER.encode(), b"License :: Other/Proprietary License")
    with zipfile.ZipFile(archive, "w") as wheel:
        for path, content in files.items():
            wheel.writestr(path, content)
    with pytest.raises(ValueError, match="classifier"):
        distribution.check_archive(archive, {"LICENSE": (distribution.ROOT / "LICENSE").read_bytes()})


def test_archive_preserves_original_grant_and_attribution(tmp_path):
    expected = distribution.project_license_files()
    distribution.check_archive(make_wheel(tmp_path), expected)
    with pytest.raises(ValueError, match="Missing or altered notice"):
        distribution.check_archive(make_wheel(tmp_path, own_notice=b"Attribution removed"), expected)


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
