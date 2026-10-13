"""User-service and migration boundaries. Never activate real host services."""
from __future__ import annotations

import json
import os
from pathlib import Path
import plistlib
import signal
import socket
import subprocess
import sys
import time

import pytest

from mia import operations
from mia.installation import apply_service_plan, service_plan
from mia.operations import Manager, OperationError
from test_operations import managed, populate


def test_service_plan_exact_review_hash_and_user_scope(managed, tmp_path, monkeypatch):
    home = tmp_path / "home"
    plan = service_plan(managed, "systemd", home=home)
    assert plan["scope"] == "current-user" and not plan["network_changes"]
    assert "Restart=no" in plan["content"] and "service-run" in plan["content"]
    assert "linger" in plan["availability"]
    commands = []
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: commands.append(command))
    changed = {**plan, "content": plan["content"] + "ExecStart=/tmp/evil\n"}
    with pytest.raises(OperationError, match="Plano mudou"):
        apply_service_plan(managed, changed, approve_sha256=plan["sha256"], home=home)
    assert not home.exists() and not commands
    result = apply_service_plan(managed, plan, approve_sha256=plan["sha256"], home=home)
    assert result["applied"] and commands == plan["commands"]
    assert Path(plan["destination"]).stat().st_mode & 0o077 == 0
    Path(plan["destination"]).write_text("other installation")
    with pytest.raises(OperationError, match="não foi substituído"):
        apply_service_plan(managed, plan, approve_sha256=plan["sha256"], home=home)
    assert Path(plan["destination"]).read_text() == "other installation"


def test_launchd_plan_is_distinct_and_has_one_bounded_retry_controller(managed, tmp_path):
    plan = service_plan(managed, "launchd", home=tmp_path)
    plist = plistlib.loads(plan["content"].encode())
    assert plist["RunAtLoad"] and not plist["KeepAlive"]
    assert plist["ProgramArguments"][-1] == "service-run"
    assert plist["Label"] in plan["destination"]
    assert plan["commands"][-1][0:2] == ["launchctl", "bootstrap"]


def test_old_managed_bootstrap_cannot_receive_unsupported_service_plan(managed, tmp_path):
    config = operations._read(managed.root / "installation.json")
    config.pop("manager_protocol")
    config.pop("manager_sha256")
    operations._write(managed.root / "installation.json", config)
    with pytest.raises(OperationError, match="Atualizar o app não atualiza manager.py"):
        service_plan(managed, "systemd", home=tmp_path)
    assert not (tmp_path / ".config").exists()


def test_stop_durably_pauses_and_start_explicitly_resumes(managed):
    assert managed.stop()["paused"]
    assert not managed.start()["paused"]


def test_manual_migration_preserves_all_private_data_and_source(managed, monkeypatch, tmp_path):
    directory = populate(managed, monkeypatch)
    source = tmp_path / "manual-data"
    operations._copy_private(directory, source)
    for path in directory.iterdir():
        if path.is_dir():
            import shutil
            shutil.rmtree(path)
        else:
            path.unlink()
    before = operations._manifest(source)
    env = tmp_path / "old.env"
    env.write_text("MIA_AI_ENABLED=false\nMIA_COOKIE_SECURE=false\n")
    with pytest.raises(OperationError, match="source-stopped"):
        managed.migrate_data(source)
    managed.migrate_data(source, source_stopped=True, source_env_file=env)
    target = managed._path(managed.active()["data"])
    assert target != source
    assert operations._manifest(source) == before
    assert {name: value for name, value in operations._manifest(target).items() if not name.startswith("mia.db")} == {name: value for name, value in before.items() if not name.startswith("mia.db")}
    import sqlite3
    with sqlite3.connect(target / "mia.db") as database:
        assert database.execute("SELECT title FROM tasks").fetchone() == ("Preservar",)
    assert (target / "ai-settings.json").read_text() == (source / "ai-settings.json").read_text()
    snapshot = managed._verify_snapshot(operations._read(managed.root / "migration.json")["snapshot"])
    assert snapshot.stat().st_mode & 0o077 == 0
    assert (snapshot / "data/notes/snapshot.json").exists()
    with pytest.raises(OperationError, match="dados gerenciados vazios"):
        managed.migrate_data(source, source_stopped=True)


def test_interrupted_verified_migration_recovers_same_private_target(managed, monkeypatch, tmp_path):
    directory = populate(managed, monkeypatch)
    source = tmp_path / "old-data"
    operations._copy_private(directory, source)
    import shutil
    shutil.rmtree(directory)
    directory.mkdir()
    original = managed._complete_migration
    monkeypatch.setattr(managed, "_complete_migration", lambda _migration: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        managed.migrate_data(source, source_stopped=True)
    assert managed.status()["recovery_required"]
    with pytest.raises(OperationError, match="recover"):
        managed._pending()
    pending = operations._read(managed.root / "migration-pending.json")
    monkeypatch.setattr(managed, "_complete_migration", original)
    managed.recover()
    assert managed.active()["data"] == pending["data"]
    assert not managed.status()["recovery_required"]
    assert (managed._path(managed.active()["data"]) / "notes/snapshot.json").exists()


def test_snapshot_excludes_unapproved_upload_staging_only(managed, monkeypatch):
    data = populate(managed, monkeypatch)
    staging = data / "migration-staging"
    staging.mkdir()
    (staging / "unapproved.txt").write_text("synthetic unapproved input")
    snapshot = managed._verify_snapshot(managed._snapshot(managed.active(), "retention-test"))
    assert not (snapshot / "data/migration-staging").exists()
    assert (data / "migration-staging/unapproved.txt").exists()
    assert (snapshot / "data/notes/snapshot.json").exists()


def wait_for(condition, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    pytest.fail("isolated background process did not reach expected state")


def healthy_idle(manager):
    return manager.status()["running"] and not operations._busy(manager.root / "operation.lock")


@pytest.fixture
def live_runner(managed, monkeypatch):
    """Use installed test runtime, no package downloads or host registration."""
    installed = subprocess.check_output([sys.executable, "-I", "-c", "import mia; print(mia.__version__)"], text=True).strip()
    release = managed._path(managed.active()["release"])
    # Reuse the entire installed environment (including pyvenv.cfg/site-packages),
    # not just its Python symlink, which would fall back to the base interpreter.
    (release / "venv").symlink_to(Path(sys.prefix), target_is_directory=True)
    operations._write(managed.root / "active.json", {**managed.active(), "version": installed})
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    config = operations._read(managed.root / "installation.json")
    operations._write(managed.root / "installation.json", {**config, "port": port})
    monkeypatch.undo()  # restore real _start/_release; subprocess uses manager copy.
    runners = []
    def launch():
        log = (managed.root / "test-runner.log").open("ab")
        process = subprocess.Popen([sys.executable, str(managed.root / "manager.py"), "--root", str(managed.root), "service-run"], stdout=log, stderr=log, start_new_session=True)
        log.close()
        runners.append(process)
        return process
    try:
        yield managed, launch
    finally:
        for runner in runners:
            if runner.poll() is None:
                runner.terminate()
                try:
                    runner.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(runner.pid, signal.SIGKILL)
                    runner.wait()
        managed.stop()


def test_runner_survives_invoking_terminal_then_host_stop_resumes_next_session(live_runner):
    manager, launch = live_runner
    runner = launch()
    wait_for(lambda: healthy_idle(manager))
    # subprocess has its own session; closing an invoking terminal/session does
    # not send SIGHUP to it. Actual SSH/OS boot still has a separate release gate.
    assert os.getsid(runner.pid) == runner.pid
    runner.terminate()
    runner.wait(timeout=30)
    assert not manager.status()["running"]
    assert not manager.status()["paused"]
    launch()
    wait_for(lambda: healthy_idle(manager))
    manager.stop()
    time.sleep(1.5)
    assert not manager.status()["running"] and manager.status()["paused"]
    manager.start()
    wait_for(lambda: healthy_idle(manager))


def test_command_exit_leaves_backend_running_and_runner_adopts_it(live_runner):
    manager, launch = live_runner
    # The invoking process really exits; only detached backend survives. This
    # exercises process lifecycle, not a claim about real SSH or machine boot.
    command = subprocess.run([sys.executable, str(manager.root / "manager.py"), "--root", str(manager.root), "start"], check=True, capture_output=True, text=True)
    assert json.loads(command.stdout)["running"]
    record = manager._record()
    assert record and os.getsid(record["pid"]) == record["pid"]
    data = manager._path(manager.active()["data"])
    (data / "synthetic-context.txt").write_text("Preserve across session and background restart")
    runner = launch()
    wait_for(lambda: manager.status()["background_service"])
    assert manager._record()["pid"] == record["pid"]
    runner.terminate()
    runner.wait(timeout=30)
    launch()
    wait_for(lambda: healthy_idle(manager))
    assert (data / "synthetic-context.txt").read_text() == "Preserve across session and background restart"


def test_runner_bounds_crash_retries_and_does_not_restart_during_maintenance(live_runner):
    manager, launch = live_runner
    launch()
    wait_for(lambda: healthy_idle(manager))
    with operations._lock(manager.root / "operation.lock"):
        record = manager._record()
        os.kill(record["child_pid"], signal.SIGKILL)
        wait_for(lambda: not manager.status()["running"])
        time.sleep(1.2)
        assert not manager.status()["running"]
        assert not manager.status()["restart_blocked"]
    wait_for(lambda: healthy_idle(manager))
    for _ in range(3):
        record = manager._record()
        os.kill(record["child_pid"], signal.SIGKILL)
        wait_for(lambda: not manager.status()["running"] or manager._record().get("child_pid") != record["child_pid"])
        if manager.status()["restart_blocked"]:
            break
        wait_for(lambda: healthy_idle(manager) or manager.status()["restart_blocked"])
        if manager.status()["restart_blocked"]:
            break
    wait_for(lambda: manager.status()["restart_blocked"])
    assert not manager.status()["running"]
    manager.start()
    assert manager.status()["running"] and not manager.status()["restart_blocked"]


