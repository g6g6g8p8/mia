"""SQLite/WAL lifecycle across short-lived manager readers and real writers."""
from __future__ import annotations

from contextlib import closing
import gc
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from mia.operations import Manager
from test_operations import managed, populate


WRITER = r'''
import sqlite3, sys
db = sqlite3.connect(sys.argv[1], isolation_level=None)
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA foreign_keys=ON")
generation = int(sys.argv[2])
# Grow both ordinary and FTS pages, as new versions/migration indexes do.
db.execute("CREATE TABLE IF NOT EXISTS lifecycle_payload(id INTEGER PRIMARY KEY, content TEXT)")
db.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS lifecycle_fts_{generation} USING fts5(content)")
for index in range(40):
    content = (f"generation{generation} item{index} " * 300)
    db.execute("INSERT INTO lifecycle_payload(content) VALUES(?)", (content,))
    db.execute(f"INSERT INTO lifecycle_fts_{generation}(content) VALUES(?)", (content,))
print("ready", flush=True)
sys.stdin.readline()
db.close()
'''


def test_update_restart_snapshot_restore_keep_wal_and_fts_consistent(managed, monkeypatch):
    """An idle reader must not retain a stale WAL mapping across worker exits.

    Disable cyclic GC to exercise actual connection lifetime boundaries; Python's
    SQLite transaction context does not close its connection on context exit.
    Each worker owns a real connection in a different process, keeps it open
    during manager reads, and closes it before the next worker starts.
    """
    populate(managed, monkeypatch)
    worker = None
    generation = 0

    def stop():
        nonlocal worker
        if worker:
            worker.stdin.write("stop\n")
            worker.stdin.flush()
            assert worker.wait(timeout=10) == 0
            for stream in (worker.stdin, worker.stdout, worker.stderr):
                stream.close()
            worker = None

    def start(**_kwargs):
        nonlocal worker, generation
        assert worker is None
        generation += 1
        database = managed._path(managed.active()["data"]) / "mia.db"
        worker = subprocess.Popen(
            [sys.executable, "-c", WRITER, str(database), str(generation)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
        )
        assert worker.stdout.readline().strip() == "ready"

    monkeypatch.setattr(managed, "_stop", stop)
    monkeypatch.setattr(managed, "_start", start)
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        start()
        managed.update(Path("unused"))
        # This restart creates new WAL/SHM files at the same database pathname.
        stop()
        start()
        managed._idle_database(managed.active())
        managed.update(Path("unused"))
        active = managed.active()
        current = managed._path(active["data"]) / "mia.db"
        with closing(sqlite3.connect(current.as_uri() + "?mode=ro", uri=True)) as db:
            assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            assert db.execute("SELECT count(*) FROM lifecycle_payload").fetchone() == (160,)
            assert db.execute("SELECT count(*) FROM lifecycle_fts_3 WHERE lifecycle_fts_3 MATCH 'generation3'").fetchone() == (40,)
        snapshot = managed._path(json.loads((managed.root / "last-update.json").read_text())["snapshot"])
        Manager._verify_db(snapshot / "data/mia.db")
        managed.rollback(acknowledge_post_update_loss=True)
        restored = managed._path(managed.active()["data"]) / "mia.db"
        with closing(sqlite3.connect(restored.as_uri() + "?mode=ro", uri=True)) as db:
            assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            # Snapshot included generations 1–3; restored startup added 5.
            assert db.execute("SELECT count(*) FROM lifecycle_payload").fetchone() == (160,)
            assert db.execute("SELECT count(*) FROM lifecycle_fts_3 WHERE lifecycle_fts_3 MATCH 'generation3'").fetchone() == (40,)
            assert db.execute("SELECT count(*) FROM sessions").fetchone() == (0,)
    finally:
        stop()
        gc.collect()
        if gc_was_enabled:
            gc.enable()
