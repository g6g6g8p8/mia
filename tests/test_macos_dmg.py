"""Fault-injected native tool contracts; fixtures are never claimed Mac DMGs."""
from pathlib import Path
import os
import subprocess

import pytest

from scripts import create_macos_dmg


@pytest.fixture
def build_paths(tmp_path):
    staging = tmp_path / "dmg-root"
    staging.mkdir()
    return staging, tmp_path / "Mia-Development-fixture.dmg"


def result(command, status=0, stderr="", stdout="native progress\n"):
    return subprocess.CompletedProcess(command, status, stdout, stderr)


def test_success_calls_absolute_system_tool_without_retry_and_preserves_progress(build_paths, capsys):
    staging, output = build_paths
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        assert command == ["/usr/bin/hdiutil", "create", "-volname", "Mia", "-srcfolder", str(staging), "-format", "UDZO", "-o", str(output)]
        output.write_bytes(b"synthetic image; not a native DMG")
        return result(command, stderr="native warning\n")
    assert create_macos_dmg.create_image(staging, output, runner=runner, wait=lambda _: pytest.fail("unexpected retry")) == 0
    assert len(calls) == 1
    captured = capsys.readouterr()
    assert captured.out == "native progress\n" and captured.err == "native warning\n"


def test_known_busy_retries_are_bounded_and_remove_only_owned_regular_partial(build_paths, capsys):
    staging, output = build_paths
    retained = staging.parent / "unrelated-private-fixture"
    retained.write_bytes(b"preserve unrelated data")
    calls, delays = [], []
    def runner(command, **kwargs):
        assert not output.exists(), "the verified previous partial must be removed before retry"
        calls.append(command)
        output.write_bytes(b"partial" if len(calls) < 3 else b"complete synthetic image")
        return result(command, 1 if len(calls) < 3 else 0, create_macos_dmg.RESOURCE_BUSY + "\n" if len(calls) < 3 else "")
    assert create_macos_dmg.create_image(staging, output, runner=runner, wait=delays.append) == 0
    assert len(calls) == 3 and delays == [2, 4]
    assert output.read_bytes() == b"complete synthetic image"
    assert retained.read_bytes() == b"preserve unrelated data"
    assert capsys.readouterr().err.count(create_macos_dmg.RESOURCE_BUSY) == 2


def test_busy_exhaustion_keeps_last_native_failure_and_partial(build_paths):
    staging, output = build_paths
    calls, delays = [], []
    def runner(command, **kwargs):
        calls.append(command)
        assert not output.exists()
        output.write_bytes(b"partial for review")
        return result(command, 1, create_macos_dmg.RESOURCE_BUSY + "\n")
    assert create_macos_dmg.create_image(staging, output, runner=runner, wait=delays.append) == 1
    assert len(calls) == 3 and delays == [2, 4]
    assert output.read_bytes() == b"partial for review"


@pytest.mark.parametrize("status,stderr", [
    (16, create_macos_dmg.RESOURCE_BUSY + "\n"),
    (1, "hdiutil: create failed - Permission denied\n"),
    (1, create_macos_dmg.RESOURCE_BUSY + "\nadditional error condition\n"),
    (9, "hdiutil: create failed - No space left on device\n"),
    (1, "prefix " + create_macos_dmg.RESOURCE_BUSY + "\n"),
])
def test_other_native_errors_do_not_retry_or_erase_partial(build_paths, status, stderr, capsys):
    staging, output = build_paths
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        output.write_bytes(b"failed image retained")
        return result(command, status, stderr)
    assert create_macos_dmg.create_image(staging, output, runner=runner, wait=lambda _: pytest.fail("unexpected retry")) == status
    assert len(calls) == 1 and output.read_bytes() == b"failed image retained"
    assert capsys.readouterr().err == stderr


@pytest.mark.parametrize("kind", ["file", "symlink", "hardlink"])
def test_existing_outputs_are_preserved_before_tool_execution(build_paths, kind):
    staging, output = build_paths
    other = staging.parent / "existing-other-file"
    other.write_bytes(b"existing data")
    if kind == "file":
        output.write_bytes(b"existing image")
    elif kind == "symlink":
        output.symlink_to(other)
    else:
        os.link(other, output)
    with pytest.raises(create_macos_dmg.ImageError, match="already exists"):
        create_macos_dmg.create_image(staging, output, runner=lambda *args, **kwargs: pytest.fail("native tool must not run"))
    assert other.read_bytes() == b"existing data"
    assert output.exists()


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "directory", "fifo", "foreign_owned"])
def test_busy_retry_refuses_unsafe_partial_without_following_or_removing_it(build_paths, kind, monkeypatch):
    staging, output = build_paths
    other = staging.parent / "private-other-file"
    other.write_bytes(b"keep private data")
    calls = []
    if kind == "foreign_owned":
        original_metadata = create_macos_dmg._metadata
        def foreign_metadata(directory, name):
            metadata = original_metadata(directory, name)
            if metadata is None:
                return None
            fields = list(metadata)
            fields[4] = os.getuid() + 1
            return os.stat_result(fields)
        monkeypatch.setattr(create_macos_dmg, "_metadata", foreign_metadata)
    def runner(command, **kwargs):
        calls.append(command)
        if kind == "symlink":
            output.symlink_to(other)
        elif kind == "hardlink":
            os.link(other, output)
        elif kind == "directory":
            output.mkdir()
        elif kind == "fifo":
            os.mkfifo(output)
        else:
            output.write_bytes(b"foreign-owned metadata fixture")
        return result(command, 1, create_macos_dmg.RESOURCE_BUSY + "\n")
    assert create_macos_dmg.create_image(staging, output, runner=runner, wait=lambda _: pytest.fail("unsafe retry")) == 1
    assert len(calls) == 1 and os.path.lexists(output)
    assert other.read_bytes() == b"keep private data"


def test_tool_success_without_regular_output_is_fatal(build_paths):
    staging, output = build_paths
    with pytest.raises(create_macos_dmg.ImageError, match="did not produce"):
        create_macos_dmg.create_image(staging, output, runner=lambda command, **kwargs: result(command))


def test_build_directory_writable_by_other_users_is_rejected(build_paths):
    staging, output = build_paths
    staging.parent.chmod(0o777)
    with pytest.raises(create_macos_dmg.ImageError, match="forbid writes"):
        create_macos_dmg.create_image(staging, output, runner=lambda *args, **kwargs: pytest.fail("unsafe build directory"))


@pytest.mark.parametrize("native_status,shell_status", [(7, 7), (-15, 143)])
def test_cli_preserves_native_failure_status(build_paths, monkeypatch, native_status, shell_status):
    staging, output = build_paths
    monkeypatch.setattr(create_macos_dmg.sys, "argv", ["create_macos_dmg.py", "--source", str(staging), "--output", str(output)])
    monkeypatch.setattr(create_macos_dmg, "create_image", lambda *args, **kwargs: native_status)
    with pytest.raises(SystemExit) as failure:
        create_macos_dmg.main()
    assert failure.value.code == shell_status
