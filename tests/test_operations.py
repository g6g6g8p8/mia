"""Offline behavior tests. Real venv/HTTP lifecycle: scripts/native_lifecycle.py."""
import json
import os
from pathlib import Path
import sqlite3

import pytest

from mia import operations
from mia.operations import Manager, OperationError


@pytest.fixture
def managed(tmp_path, monkeypatch):
    manager = Manager(tmp_path / "installation")
    sequence = iter(("0.2.0a10", "0.2.0a11", "0.2.0a12"))
    def release(_source, _wheelhouse=None, _offline=False):
        version = next(sequence)
        path = manager.root / "releases" / version
        path.mkdir()
        return {"release": "releases/" + version, "version": version}
    monkeypatch.setattr(manager, "_release", release)
    manager.install(Path(__file__).resolve().parents[1])
    monkeypatch.setattr(manager, "_start", lambda **kwargs: None)
    return manager


def populate(manager, monkeypatch):
    monkeypatch.setenv("MIA_DATA_DIR", str(manager._path(manager.active()["data"])))
    from mia import db
    from mia.security import iso
    db.initialize()
    with db.connect() as database:
        database.execute("INSERT INTO owner(id,name,email,timezone,password_hash,created_at) VALUES(1,'Sintético','synthetic@example.test','UTC','not-a-real-password',?)", (iso(),))
        database.execute("INSERT INTO areas(id,owner_id,name,description,color,created_at,updated_at) VALUES('a',1,'Teste','','slate',?,?)", (iso(), iso()))
        database.execute("INSERT INTO tasks(id,owner_id,area_id,title,notes,priority,status,created_at,updated_at) VALUES('t',1,'a','Preservar','','1','open',?,?)", (iso(), iso()))
        database.execute("INSERT INTO sessions(token_hash,owner_id,expires_at,created_at,last_seen_at) VALUES('synthetic',1,'2099-01-01',?,?)", (iso(), iso()))
    directory = manager._path(manager.active()["data"])
    (directory / "ai-settings.json").write_text(json.dumps({"api_key": "synthetic-not-a-credential", "model": "local-test"}))
    (directory / "access-settings.json").write_text('{"mode":"local"}')
    (directory / "notes").mkdir()
    (directory / "notes/snapshot.json").write_text("Private synthetic extra file")
    return directory


def test_install_is_empty_private_and_refuses_existing_directory(managed):
    assert list(managed._path(managed.active()["data"]).iterdir()) == []
    assert managed.root.stat().st_mode & 0o077 == 0
    assert (managed.root / "machine.env").stat().st_mode & 0o077 == 0
    with pytest.raises(OperationError, match="diretório novo"):
        managed.install(Path(__file__).resolve().parents[1])


def test_update_and_rollback_keep_full_configuration_and_post_update_data(managed, monkeypatch):
    original = populate(managed, monkeypatch)
    managed.update(Path("unused"))
    assert managed.active()["version"] == "0.2.0a11"
    (original / "after-update.txt").write_text("New changes must survive rollback")
    (managed.root / "machine.env").write_text("MIA_AI_ENABLED=true\n")
    with pytest.raises(OperationError, match="alterações posteriores"):
        managed.rollback()
    managed.rollback(acknowledge_post_update_loss=True)
    active = managed.active()
    restored = managed._path(active["data"])
    assert active["version"] == "0.2.0a10"
    assert restored != original
    assert (original / "after-update.txt").exists()
    assert not (restored / "after-update.txt").exists()
    assert (restored / "ai-settings.json").read_text() == (original / "ai-settings.json").read_text()
    assert (restored / "notes/snapshot.json").read_text() == "Private synthetic extra file"
    assert "MIA_AI_ENABLED=false" in (managed.root / "machine.env").read_text()
    with sqlite3.connect(restored / "mia.db") as db:
        assert db.execute("SELECT title FROM tasks").fetchone() == ("Preservar",)
        assert db.execute("SELECT count(*) FROM sessions").fetchone() == (0,)
    retained = list((managed.root / "snapshots").glob("before-rollback-*"))[0]
    assert (retained / "data/after-update.txt").exists()
    assert "MIA_AI_ENABLED=true" in (retained / "machine.env").read_text()
    with pytest.raises(OperationError, match="já foi revertida"):
        managed.rollback(acknowledge_post_update_loss=True)


def test_interruption_after_switch_requires_recovery_into_fresh_data(managed, monkeypatch):
    original = populate(managed, monkeypatch)
    write = operations._write
    def crash(path, value):
        write(path, value)
        if path == managed.root / "active.json" and value["version"] == "0.2.0a11":
            raise KeyboardInterrupt("simulated hard interruption")
    monkeypatch.setattr(operations, "_write", crash)
    with pytest.raises(KeyboardInterrupt):
        managed.update(Path("unused"))
    assert managed.status()["recovery_required"]
    monkeypatch.setattr(operations, "_write", write)
    with pytest.raises(OperationError, match="recover"):
        managed._pending()
    with sqlite3.connect(original / "mia.db") as db:
        db.execute("CREATE TABLE simulated_migration(value TEXT)")
    managed.recover()
    restored = managed._path(managed.active()["data"])
    assert restored != original
    with sqlite3.connect(restored / "mia.db") as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='simulated_migration'").fetchone()
    assert not managed.status()["recovery_required"]
    # Recovery with no journal is safe to repeat and does not restore again.
    managed.recover()
    assert managed._path(managed.active()["data"]) == restored


def test_failed_startup_restores_old_release_and_preserves_attempt_database(managed, monkeypatch):
    original = populate(managed, monkeypatch)
    def start(**kwargs):
        if managed.active()["version"] == "0.2.0a11":
            (original / "new-version-output.txt").write_text("attempt retained")
            raise OperationError("bad release startup")
    monkeypatch.setattr(managed, "_start", start)
    with pytest.raises(OperationError, match="versão anterior restaurada"):
        managed.update(Path("unused"))
    assert managed.active()["version"] == "0.2.0a10"
    assert managed._path(managed.active()["data"]) != original
    assert (original / "new-version-output.txt").exists()
    assert not (managed.root / "journal.json").exists()


def test_tampered_snapshot_fails_closed_and_keeps_journal(managed, monkeypatch):
    populate(managed, monkeypatch)
    managed.update(Path("unused"))
    prior = operations._read(managed.root / "last-update.json")
    snapshot = managed._path(prior["snapshot"])
    (snapshot / "data/notes/snapshot.json").write_text("tampered")
    operations._write(managed.root / "journal.json", prior)
    active = managed.active()
    with pytest.raises(OperationError, match="alterado"):
        managed.recover()
    assert managed.active() == active
    assert managed.status()["recovery_required"]


def test_running_generation_blocks_update_before_install_or_stop(managed, monkeypatch):
    original = populate(managed, monkeypatch)
    with sqlite3.connect(original / "mia.db") as db:
        db.execute("INSERT INTO runs(id,owner_id,request_key,request_json,state,model,endpoint,sources_json,created_at,updated_at) VALUES('r',1,'key','{}','running','synthetic','http://127.0.0.1','[]','now','now')")
    with pytest.raises(OperationError, match="geração"):
        managed.update(Path("unused"))
    assert managed.active()["version"] == "0.2.0a10"
    assert len(list((managed.root / "releases").iterdir())) == 1


def test_pid_reuse_or_unknown_lock_owner_is_never_signalled(managed, monkeypatch):
    operations._write(managed.root / "process.json", {"pid": os.getpid(), "birth": "wrong-birth"})
    monkeypatch.setattr(operations, "_busy", lambda path: True)
    monkeypatch.setattr(os, "kill", lambda *_: pytest.fail("Must never signal another process"))
    with pytest.raises(OperationError, match="identidade verificável"):
        managed._stop()


def test_external_config_shell_commands_and_secret_exposure_are_rejected(managed, monkeypatch, tmp_path):
    shell = tmp_path / "bad.env"
    shell.write_text("PYTHONPATH=/tmp/evil\n")
    with pytest.raises(OperationError, match="somente variáveis"):
        operations._validate_env(shell)
    shell.write_text("MIA_DATA_DIR=/tmp/other\n")
    with pytest.raises(OperationError):
        operations._validate_env(shell)
    monkeypatch.setenv("MIA_OPERATIONS_ROOT", str(managed.root))
    status = json.dumps(operations.public_status())
    assert str(managed.root) not in status
    assert "api_key" not in status


def test_symlinked_private_files_are_not_followed(managed, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "secret").symlink_to(managed.root / "machine.env")
    with pytest.raises(OperationError, match="Links simbólicos"):
        operations._copy_private(source, tmp_path / "copy")


def test_install_lockfile_must_pin_every_dependency(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "mia").mkdir()
    (source / "pyproject.toml").write_text('[project]\nname="mia-personal-ai"\nversion="0.2.0a10"\n')
    (source / "requirements.lock").write_text('httpx>=0.28\n')
    manager = Manager(tmp_path / "installation")
    with pytest.raises(OperationError, match="fixar todas as versões"):
        manager.install(source)
    assert not list((manager.root / "releases").iterdir())
