"""Portable ownership/provenance checks; these do not substitute for Mac CI."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from scripts.native_mac_acceptance import fixture, run as webkit_run, verify_source_binding, write_new
from scripts.native_mac_service_acceptance import run as service_run
from scripts.package_macos import copy_public_source, source_provenance


def git(source: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(source), "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=Synthetic fixture", "-c", "user.email=synthetic@example.invalid", *arguments], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def test_fixture_never_archives_outside_directory_symlink(tmp_path):
    archive, folder = fixture(tmp_path)
    assert (folder / "escaped.md").is_symlink()
    assert (folder / "escaped.md").resolve() == tmp_path / "outside-secret.md"
    with zipfile.ZipFile(archive) as compressed:
        assert set(compressed.namelist()) == {"Aurora/decisao.md", "Aurora/pendencia.md", "Aurora/.obsidian/app.json"}


def test_receipts_and_logs_are_new_private_files_and_never_follow_links(tmp_path):
    original = tmp_path / "evidence.log"
    write_new(original, "synthetic original")
    assert original.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_new(original, "overwrite")
    substituted = tmp_path / "substituted.log"
    substituted.symlink_to(original)
    with pytest.raises(FileExistsError):
        write_new(substituted, "overwrite")
    assert original.read_text() == "synthetic original"


def test_native_acceptance_is_bound_to_clean_native_revision_and_bundled_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("Synthetic acceptance fixture.\n")
    (source / "mia").mkdir()
    (source / "mia/__init__.py").write_text('__version__ = "0.2.0a14"\n')
    native = source / "macos/Mia/Sources/Mia/MiaWebView.swift"
    native.parent.mkdir(parents=True)
    native.write_text("// Synthetic reviewed native source\n")
    git(source, "init")
    git(source, "add", ".")
    git(source, "commit", "-m", "Synthetic acceptance input")
    app = tmp_path / "Mia.app"
    resources = app / "Contents/Resources"
    resources.mkdir(parents=True)
    copy_public_source(source, resources / "source")
    provenance = source_provenance(source, resources / "source")
    (resources / "build-report.json").write_text(json.dumps({"source_provenance": provenance}))
    assert verify_source_binding(app, source) == git(source, "rev-parse", "HEAD")
    native.write_text("// Same version, different native coordinator\n")
    with pytest.raises(AssertionError, match="reviewed Git revision"):
        verify_source_binding(app, source)
    git(source, "checkout", "--", str(native.relative_to(source)))
    (resources / "source/mia/__init__.py").write_text('__version__ = "same-version-changed-bytes"\n')
    with pytest.raises(AssertionError, match="source inventory"):
        verify_source_binding(app, source)


@pytest.mark.skipif(sys.platform == "darwin", reason="Actual native paths must be exercised by Mac acceptance CI.")
def test_linux_cannot_publish_native_webkit_or_launchd_evidence(tmp_path):
    for runner in (webkit_run, service_run):
        with pytest.raises(RuntimeError, match="requires macOS"):
            runner(tmp_path / "missing-app", tmp_path / "missing-source", tmp_path / "evidence.json")
    assert not (tmp_path / "evidence.json").exists()
