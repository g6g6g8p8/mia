"""Opt-in local snapshots while the single-worker application is running."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
import tempfile
import threading
import uuid

from pydantic import BaseModel, ConfigDict, Field

from .backup import snapshot
from .db import data_dir

LOCK = threading.RLock()
NAME = re.compile(r'mia-auto-\d{8}T\d{12}Z-[a-f0-9]{32}\.db')


class Policy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = False
    keep: int = Field(default=7, ge=1, le=30)


def _read(name, default):
    path = data_dir() / name
    return json.loads(path.read_text()) if path.exists() else default


def _write(name, values):
    fd, temporary = tempfile.mkstemp(prefix='backup-state-', dir=data_dir())
    try:
        with os.fdopen(fd, 'w') as file:
            json.dump(values, file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, data_dir() / name)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _files():
    directory = data_dir() / 'auto-backups'
    if not directory.exists():
        return []
    return sorted((p for p in directory.iterdir() if NAME.fullmatch(p.name) and p.is_file() and not p.is_symlink()), reverse=True)


def status():
    with LOCK:
        policy = Policy.model_validate(_read('backup-policy.json', {}))
        state = _read('backup-status.json', {})
        return {**policy.model_dump(), **state, 'files': [dict(name=p.name, bytes=p.stat().st_size) for p in _files()]}


def configure(policy):
    with LOCK:
        _write('backup-policy.json', policy.model_dump())
        return status()


def run(force=False, clock=None):
    with LOCK:
        policy = Policy.model_validate(_read('backup-policy.json', {}))
        state = _read('backup-status.json', {})
        now = clock or datetime.now(timezone.utc)
        if not force:
            if not policy.enabled:
                return False
            if state.get('last_attempt') and now - datetime.fromisoformat(state['last_attempt']) < timedelta(hours=24 if not state.get('error') else 1):
                return False
        state['last_attempt'] = now.isoformat()
        directory = data_dir() / 'auto-backups'
        token = uuid.uuid4().hex
        temporary = directory / ('.pending-' + token + '.db')
        destination = directory / ('mia-auto-' + now.strftime('%Y%m%dT%H%M%S%fZ') + '-' + token + '.db')
        try:
            directory.mkdir(mode=0o700, exist_ok=True)
            snapshot(temporary)
            os.replace(temporary, destination)
            state.update(last_success=now.isoformat(), error=None)
            # Prune only our own snapshots, and only after a verified new copy.
            for old in _files()[policy.keep:]:
                old.unlink()
            _write('backup-status.json', state)
            return True
        except Exception:
            state['error'] = 'Backup ou retenção não concluído. Confira espaço e permissões da instalação.'
            _write('backup-status.json', state)
            logging.getLogger(__name__).exception('Local backup failed')
            raise
        finally:
            temporary.unlink(missing_ok=True)


def open_snapshot(name):
    with LOCK:
        if not NAME.fullmatch(name):
            raise FileNotFoundError
        path = data_dir() / 'auto-backups' / name
        if path.is_symlink():
            raise FileNotFoundError
        return path.open('rb')


async def worker(stop):
    while not stop.is_set():
        try:
            await asyncio.to_thread(run)
        except Exception:
            logging.getLogger(__name__).error('Automatic backup check failed; see backup status')
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
