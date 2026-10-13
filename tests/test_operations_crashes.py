"""Adversarial operation boundaries; all data/processes are temporary.

Release preparation is stubbed here. These tests exercise durable state and real
Unix lock/process behavior; they do not replace installed-package lifecycle
validation.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import textwrap
import time

import pytest

from mia import operations
from mia.operations import Manager, OperationError
from test_operations import managed, populate


def test_external_serve_is_refused_during_operation(managed, monkeypatch):
    """A service/manual start cannot enter the stop-to-journal update gap."""
    monkeypatch.setattr(
        operations.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("Concurrent serve spawned a worker"),
    )
    with operations._lock(managed.root / "operation.lock"):
        with pytest.raises(OperationError):
            managed.serve()
    assert not (managed.root / "process.json").exists()
    assert not operations._busy(managed.root / "service.lock")


def test_existing_same_version_different_release_cannot_confirm_start(managed, monkeypatch):
    """HTTP version alone cannot identify a newly deployed same-version build."""
    active = managed.active()
    record = {
        "pid": os.getpid(), "birth": operations._birth(os.getpid()),
        "child_pid": os.getpid(), "child_birth": operations._birth(os.getpid()),
        "ready": True, "version": active["version"],
        "release": "releases/another-build-with-the-same-version",
        "data": active["data"],
    }
    monkeypatch.setattr(managed, "_record", lambda: record)
    monkeypatch.setattr(managed, "_stop", lambda: None)

    class ExistingServer:
        def open(self, url, **_kwargs):
            payload = {"ok": True, "version": active["version"]} if url.endswith('/health') else {"configured": True, "version": active["version"]}
            return contextlib.closing(io.StringIO(json.dumps(payload)))

    monkeypatch.setattr(operations.urllib.request, "build_opener", lambda *_args: ExistingServer())
    # Fail quickly if a fix merely keeps polling the same wrong process.
    ticks = iter((0, 0, 21))
    monkeypatch.setattr(operations.time, "monotonic", lambda: next(ticks, 21))
    monkeypatch.setattr(operations.time, "sleep", lambda _seconds: None)
    with pytest.raises(OperationError):
        Manager._start(managed)


def test_unavailable_process_birth_never_authorizes_a_signal(managed, monkeypatch):
    operations._write(managed.root / "process.json", {"pid": os.getpid(), "birth": None})
    monkeypatch.setattr(operations, "_busy", lambda _path: True)
    monkeypatch.setattr(operations, "_birth", lambda _pid: None)
    monkeypatch.setattr(os, "kill", lambda *_args: pytest.fail("An unknown birth is not a verified process identity"))
    with pytest.raises(OperationError):
        managed._stop()


def test_recover_resumes_same_restored_data_after_healthy_start_interruption(managed, monkeypatch):
    """Retrying the finalization must preserve the already restored database."""
    populate(managed, monkeypatch)
    managed.update(Path("unused"))
    finish = managed._finish

    def interrupted_finish(*_args):
        raise KeyboardInterrupt("Crash after restored startup, before durable finish")

    monkeypatch.setattr(managed, "_finish", interrupted_finish)
    with pytest.raises(KeyboardInterrupt):
        managed.rollback(acknowledge_post_update_loss=True)
    restored = managed.active()
    restored_data = managed._path(restored["data"])
    with sqlite3.connect(restored_data / "mia.db") as database:
        database.execute("INSERT INTO tasks(id,owner_id,area_id,title,notes,priority,status,created_at,updated_at) VALUES('accepted-after-recovery',1,'a','Keep accepted edit','','2','open','now','now')")
    (restored_data / "accepted-after-recovery.txt").write_text("Committed after restored startup")
    directories = set((managed.root / "data").iterdir())

    monkeypatch.setattr(managed, "_finish", finish)
    managed.recover()
    assert managed.active() == restored
    assert set((managed.root / "data").iterdir()) == directories
    assert (restored_data / "accepted-after-recovery.txt").read_text() == "Committed after restored startup"
    with sqlite3.connect(restored_data / "mia.db") as database:
        assert database.execute("SELECT title FROM tasks WHERE id='accepted-after-recovery'").fetchone() == ("Keep accepted edit",)
    assert not (managed.root / "journal.json").exists()


def test_recovery_target_missing_database_is_refused_instead_of_recreated_empty(managed, monkeypatch):
    populate(managed, monkeypatch)
    managed.update(Path("unused"))

    def interrupted_finish(*_args):
        raise KeyboardInterrupt("Crash before recovery finishes")

    monkeypatch.setattr(managed, "_finish", interrupted_finish)
    with pytest.raises(KeyboardInterrupt):
        managed.rollback(acknowledge_post_update_loss=True)
    restored = managed.active()
    restored_data = managed._path(restored["data"])
    (restored_data / "mia.db").unlink()
    monkeypatch.setattr(managed, "_start", lambda **_kwargs: pytest.fail("Recovery must not start an empty replacement database"))
    with pytest.raises(OperationError):
        managed.recover()
    assert (managed.root / "journal.json").exists()
    assert managed.active() == restored


def test_recovery_target_link_cannot_alias_the_migrated_database(managed, monkeypatch):
    original = populate(managed, monkeypatch)
    managed.update(Path("unused"))
    with sqlite3.connect(original / "mia.db") as database:
        database.execute("CREATE TABLE only_in_new_version(value TEXT)")

    def interrupted_finish(*_args):
        raise KeyboardInterrupt("Crash before recovery finishes")

    monkeypatch.setattr(managed, "_finish", interrupted_finish)
    with pytest.raises(KeyboardInterrupt):
        managed.rollback(acknowledge_post_update_loss=True)
    restored = managed.active()
    destination = managed.root / restored["data"]
    shutil.rmtree(destination)
    destination.symlink_to(original, target_is_directory=True)
    monkeypatch.setattr(managed, "_start", lambda **_kwargs: pytest.fail("Old release must not run on the aliased migrated database"))
    with pytest.raises(OperationError):
        managed.recover()
    assert (managed.root / "journal.json").exists()
    with sqlite3.connect(original / "mia.db") as database:
        assert database.execute("SELECT name FROM sqlite_master WHERE name='only_in_new_version'").fetchone() == ("only_in_new_version",)


def test_child_eof_before_durable_record_does_not_execute_app(managed, monkeypatch):
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    monkeypatch.setattr(os, "execv", lambda *_args: pytest.fail("Unrecorded child executed the app"))
    managed.child(ready_fd=read_fd, socket_fd=-1, service_lock_fd=-1)
    assert list(managed._path(managed.active()["data"]).iterdir()) == []


def test_sigkill_before_child_identity_record_releases_lock_without_starting_app(managed):
    """Exercise the real post-spawn/pre-record window with a waiting child."""
    active = managed.active()
    binary = managed._python(active)
    binary.parent.mkdir(parents=True)
    binary.symlink_to(sys.executable)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    installation = operations._read(managed.root / "installation.json")
    operations._write(managed.root / "installation.json", {**installation, "port": port})
    script = textwrap.dedent("""
        import os, signal, sys
        from pathlib import Path
        sys.path.insert(0, sys.argv[2])
        from mia import operations
        root = Path(sys.argv[1])
        write = operations._write
        def die_before_record(path, value):
            if path == root / 'process.json' and value.get('child_pid'):
                write(root / 'test-child.json', {'pid': value['child_pid'], 'birth': value['child_birth']})
                os.kill(os.getpid(), signal.SIGKILL)
            write(path, value)
        operations._write = die_before_record
        operations.Manager(root).serve()
    """)
    supervisor = subprocess.Popen(
        [sys.executable, "-c", script, str(managed.root), str(Path(__file__).resolve().parents[1])],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    child_record = {}
    try:
        assert supervisor.wait(timeout=10) == -signal.SIGKILL
        child_record = operations._read(managed.root / "test-child.json")
        assert child_record.get("birth")
        deadline = time.monotonic() + 5
        while operations._busy(managed.root / "service.lock") and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not operations._busy(managed.root / "service.lock")
        assert managed._record() == {}
        assert list(managed._path(active["data"]).iterdir()) == []
    finally:
        if supervisor.poll() is None:
            supervisor.kill()
            supervisor.wait(timeout=5)
        child_record = child_record or operations._read(managed.root / "test-child.json")
        pid = child_record.get("pid")
        if pid and operations._birth(pid) == child_record.get("birth"):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_orphan_worker_keeps_lock_and_can_be_stopped_by_recorded_birth(managed):
    """SIGKILL of a supervisor cannot make its living worker disappear."""
    script = textwrap.dedent("""
        import fcntl, os, signal, subprocess, sys
        from pathlib import Path
        sys.path.insert(0, sys.argv[2])
        from mia import operations
        root = Path(sys.argv[1])
        handle = (root / 'service.lock').open('a+')
        fcntl.flock(handle, fcntl.LOCK_EX)
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], pass_fds=(handle.fileno(),), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        operations._write(root / 'process.json', {
            'pid': os.getpid(), 'birth': operations._birth(os.getpid()),
            'child_pid': child.pid, 'child_birth': operations._birth(child.pid),
            'version': 'synthetic', 'ready': True,
        })
        os.kill(os.getpid(), signal.SIGKILL)
    """)
    supervisor = subprocess.Popen(
        [sys.executable, "-c", script, str(managed.root), str(Path(__file__).resolve().parents[1])],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    child_record = {}
    try:
        _, stderr = supervisor.communicate(timeout=10)
        assert supervisor.returncode == -signal.SIGKILL, stderr.decode()
        child_record = operations._read(managed.root / "process.json")
        worker = managed._record()
        assert worker["pid"] == child_record["child_pid"]
        assert worker["birth"] == child_record["child_birth"]
        assert operations._busy(managed.root / "service.lock")
        managed._stop()
        assert not operations._busy(managed.root / "service.lock")
        assert managed._record() == {}
    finally:
        if supervisor.poll() is None:
            supervisor.kill()
            supervisor.wait(timeout=5)
        child_record = child_record or operations._read(managed.root / "process.json")
        pid = child_record.get("child_pid")
        if pid and operations._birth(pid) == child_record.get("child_birth"):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
