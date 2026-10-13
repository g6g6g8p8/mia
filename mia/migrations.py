"""Bounded, local migration jobs. Upload, review and publication are distinct effects.

Raw archives and unapproved text live in private staging, never in documents or
chunks. Every published document and its checkpoint commit in one transaction.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import errno
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import struct
import threading
import uuid
import zipfile

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .db import data_dir
from .knowledge import chunk_content, normalized
from .migration_formats import iter_entry
from .security import iso

MAX_UPLOAD = 100 * 1024 * 1024
MAX_CHUNK = 1024 * 1024
MAX_FILE = 8 * 1024 * 1024
MAX_TEXT_TOTAL = 500 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024
MAX_DESCRIPTORS = 50_000
MAX_CENTRAL_BYTES = 16 * 1024 * 1024
MAX_DOCUMENTS = 50_000
MAX_OWNER_STAGING = 500 * 1024 * 1024
MAX_OWNER_STAGE_DISK = 4 * 1024 * 1024 * 1024
MAX_OWNER_TEXT = 2 * 1024 * 1024 * 1024
MAX_OWNER_DOCUMENTS = 100_000
MAX_DEPTH = 32
RETENTION_DAYS = 7
LOCKS: dict[str, threading.RLock] = {}
LOCKS_GUARD = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS migration_jobs (
 id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES owner(id),
 filename TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL,
 source_kind TEXT NOT NULL, state TEXT NOT NULL, received INTEGER NOT NULL DEFAULT 0,
 client_not_sent INTEGER NOT NULL DEFAULT 0, staging_reservation INTEGER NOT NULL DEFAULT 0,
 area_id TEXT REFERENCES areas(id), catalogued INTEGER NOT NULL DEFAULT 0,
 selection_json TEXT NOT NULL DEFAULT '{"groups":["*"],"excluded_ids":[]}',
 report_json TEXT NOT NULL DEFAULT '{}', error TEXT, retryable INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS migration_entries (
 job_id TEXT NOT NULL REFERENCES migration_jobs(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL, path TEXT NOT NULL, bytes INTEGER NOT NULL,
 category TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', reason TEXT,
 omissions_json TEXT NOT NULL DEFAULT '{}',
 PRIMARY KEY(job_id, ordinal)
);
CREATE TABLE IF NOT EXISTS migration_items (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES migration_jobs(id) ON DELETE CASCADE,
 path TEXT NOT NULL, title TEXT NOT NULL, kind TEXT NOT NULL, source_id TEXT NOT NULL,
 group_name TEXT NOT NULL, hash TEXT NOT NULL, characters INTEGER NOT NULL,
 bytes INTEGER NOT NULL, selected INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'staged', document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
 error TEXT
);
CREATE INDEX IF NOT EXISTS migration_items_job_idx ON migration_items(job_id,status,id);
CREATE INDEX IF NOT EXISTS migration_items_selection_idx ON migration_items(job_id,selected,status);
CREATE INDEX IF NOT EXISTS migration_document_hash_idx ON documents(owner_id,hash);
CREATE INDEX IF NOT EXISTS migration_document_path_idx ON documents(owner_id,path);
CREATE TABLE IF NOT EXISTS migration_storage (
 owner_id INTEGER PRIMARY KEY REFERENCES owner(id) ON DELETE CASCADE,
 document_bytes INTEGER NOT NULL DEFAULT 0,
 document_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS migration_cleanup (
 job_id TEXT PRIMARY KEY
);
CREATE TRIGGER IF NOT EXISTS migration_document_insert AFTER INSERT ON documents BEGIN
 INSERT INTO migration_storage VALUES(NEW.owner_id,length(cast(NEW.content AS BLOB)),1)
 ON CONFLICT(owner_id) DO UPDATE SET document_bytes=document_bytes+excluded.document_bytes,document_count=document_count+1;
END;
CREATE TRIGGER IF NOT EXISTS migration_document_delete AFTER DELETE ON documents BEGIN
 UPDATE migration_storage SET document_bytes=document_bytes-length(cast(OLD.content AS BLOB)),document_count=document_count-1 WHERE owner_id=OLD.owner_id;
END;
CREATE TRIGGER IF NOT EXISTS migration_document_update AFTER UPDATE OF owner_id,content ON documents BEGIN
 UPDATE migration_storage SET document_bytes=document_bytes-length(cast(OLD.content AS BLOB)),document_count=document_count-1 WHERE owner_id=OLD.owner_id;
 INSERT INTO migration_storage VALUES(NEW.owner_id,length(cast(NEW.content AS BLOB)),1)
 ON CONFLICT(owner_id) DO UPDATE SET document_bytes=document_bytes+excluded.document_bytes,document_count=document_count+1;
END;
CREATE TABLE IF NOT EXISTS migration_provenance (
 document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 import_id TEXT NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
 item_id TEXT NOT NULL, source_id TEXT NOT NULL, metadata_json TEXT NOT NULL,
 PRIMARY KEY(document_id,import_id,item_id)
);
CREATE INDEX IF NOT EXISTS migration_provenance_source_idx ON migration_provenance(source_id,document_id);
"""


class CreateUpload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filename: str = Field(min_length=1, max_length=200)
    size: int = Field(gt=0, le=MAX_UPLOAD)
    sha256: str = Field(pattern=r'^[a-fA-F0-9]{64}$')
    source_kind: str = Field(default='files', pattern=r'^(files|obsidian|chatgpt|claude|drive)$')
    client_not_sent: int = Field(default=0, ge=0, le=MAX_DESCRIPTORS)


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    groups: list[str] = Field(default_factory=lambda: ['*'], max_length=10_000)
    excluded_ids: list[str] = Field(default_factory=list, max_length=MAX_DOCUMENTS)


class Confirm(Selection):
    area_id: str | None = Field(default=None, max_length=80)


def limits():
    return dict(upload_bytes=MAX_UPLOAD, chunk_bytes=MAX_CHUNK,
                file_bytes=MAX_FILE, export_bytes=MAX_UPLOAD, text_bytes=MAX_TEXT_TOTAL,
                descriptors=MAX_DESCRIPTORS, documents=MAX_DOCUMENTS,
                depth=MAX_DEPTH, staging_days=RETENTION_DAYS)


def _directory(directory=None):
    return Path(directory).resolve() if directory is not None else data_dir()


def _connect(directory=None):
    db = sqlite3.connect(_directory(directory) / 'mia.db', timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    return db


@contextmanager
def _connection(directory=None):
    db = _connect(directory)
    try:
        yield db
    finally:
        db.close()


@contextmanager
def _transaction(directory=None):
    db = _connect(directory)
    try:
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _lock(directory=None):
    key = str(_directory(directory))
    with LOCKS_GUARD:
        return LOCKS.setdefault(key, threading.RLock())


def _stage(job, directory=None, create=False):
    # Identifiers are generated by us and never user paths.
    if not re.fullmatch(r'[a-f0-9]{32}', job):
        raise HTTPException(404, 'Migração não encontrada')
    root = _directory(directory) / 'migration-staging'
    path = root / job
    if root.is_symlink() or path.is_symlink():
        raise OSError('Staging não pode ser link simbólico')
    if create:
        root.mkdir(mode=0o700, exist_ok=True)
        os.chmod(root, 0o700)
        path.mkdir(mode=0o700, exist_ok=True)
        os.chmod(path, 0o700)
        _sync_directory(root.parent)
        _sync_directory(root)
    return path


def _open_private(path, flags):
    fd = os.open(path, flags | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise OSError('Arquivo de staging inválido')
    return fd


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    try:
        try:
            os.fsync(fd)
        except OSError as error:
            if error.errno not in (errno.EINVAL, errno.ENOTSUP):
                raise
    finally:
        os.close(fd)


def _owned(db, job, owner):
    row = db.execute('SELECT * FROM migration_jobs WHERE id=? AND owner_id=?',
                     (job, owner['id'])).fetchone()
    if row is None:
        raise HTTPException(404, 'Migração não encontrada')
    return row


def initialize(directory=None):
    with _connection(directory) as db:
        db.executescript(SCHEMA)
        if 'omissions_json' not in {r[1] for r in db.execute('PRAGMA table_info(migration_entries)')}:
            db.execute("ALTER TABLE migration_entries ADD COLUMN omissions_json TEXT NOT NULL DEFAULT '{}'")
        columns = {r[1] for r in db.execute('PRAGMA table_info(migration_jobs)')}
        for name in ('client_not_sent', 'staging_reservation'):
            if name not in columns:
                db.execute(f'ALTER TABLE migration_jobs ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0')
        db.execute('INSERT OR REPLACE INTO migration_storage SELECT o.id,coalesce(sum(length(cast(d.content AS BLOB))),0),count(d.id) FROM owner o LEFT JOIN documents d ON d.owner_id=o.id GROUP BY o.id')
    _reconcile_staging(directory)


def _complete_index(db, job):
    report = _report(db, job)
    state = 'partial' if report['entries']['errors'] or report['documents']['errors'] else 'completed'
    db.execute('UPDATE migration_jobs SET state=?,report_json=?,updated_at=? WHERE id=?', (state, json.dumps(report), iso(), job))
    db.execute("UPDATE imports SET state='completed',report_json=? WHERE id=?", (json.dumps(report), job))


def _reconcile_staging(directory=None):
    """A SQLite snapshot preserves approved effects, not private staging files."""
    clean = []
    with _lock(directory), _transaction(directory) as db:
        jobs = list(db.execute("SELECT * FROM migration_jobs WHERE state IN ('receiving','inventory','review','indexing','failed')"))
        for row in jobs:
            pending = list(db.execute("SELECT id FROM migration_items WHERE job_id=? AND status='staged'" + (" AND selected=1" if row['state'] == 'indexing' else ''), (row['id'],)))
            if row['state'] == 'indexing' and not pending:
                _complete_index(db, row['id'])
                clean.append(row['id'])
                continue
            try:
                stage = _stage(row['id'], directory)
                upload = stage / 'upload'
                unavailable = not upload.is_file() or upload.is_symlink() or upload.stat().st_size < row['received']
                unavailable |= any(not (stage / (item[0] + '.json')).is_file() or (stage / (item[0] + '.json')).is_symlink() for item in pending)
            except OSError:
                unavailable = True
            if unavailable:
                db.execute("UPDATE migration_jobs SET state='failed',retryable=0,error=?,updated_at=? WHERE id=?", ('Staging não está disponível nesta instalação restaurada. Fontes já aprovadas foram preservadas; envie o arquivo novamente em uma nova migração.', iso(), row['id']))
        clean += [r[0] for r in db.execute("SELECT id FROM migration_jobs WHERE state IN ('completed','partial','cancelled')")]
    for job in set(clean):
        try:
            _cleanup(job, directory)
        except OSError:
            logging.getLogger(__name__).error('Terminal migration staging cleanup remains pending')


def _safe_path(name):
    try:
        name.encode('utf-8')
    except UnicodeEncodeError as error:
        raise ValueError('Caminho contém Unicode inválido') from error
    if not name or '\\' in name or '\x00' in name or re.match(r'^[A-Za-z]:', name):
        raise ValueError('Caminho não permitido no ZIP')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or len(path.parts) > MAX_DEPTH or len(name) > 1024:
        raise ValueError('Caminho ou profundidade não permitidos no ZIP')
    return str(path)


def _category(path, directory=False):
    if directory:
        return 'directory', 'Pasta; não é documento'
    parts = PurePosixPath(path).parts
    if any(p.startswith('.') or p in ('__MACOSX', 'node_modules', '__pycache__') for p in parts):
        return 'ignored', 'Metadados, cache ou arquivo oculto'
    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in ('.md', '.markdown', '.txt', '.json'):
        return 'ignored', ('Atalho Google; exporte o documento como texto' if suffix in ('.gdoc', '.gsheet', '.gslides') else 'Formato não textual suportado; não indexado')
    return 'eligible', None


def _space(directory, needed):
    if shutil.disk_usage(_directory(directory)).free < needed + 32 * 1024 * 1024:
        raise HTTPException(507, 'Espaço insuficiente para staging e índice. Libere espaço antes de enviar.')


def create_upload(payload, owner, directory=None):
    try:
        name = _safe_path(payload.filename)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    if '/' in name:
        raise HTTPException(422, 'Envie um nome de arquivo, sem caminho')
    if PurePosixPath(name).suffix.lower() not in ('.zip', '.md', '.markdown', '.txt', '.json'):
        raise HTTPException(422, 'Use ZIP, Markdown, texto ou exportação JSON reconhecida')
    if PurePosixPath(name).suffix.lower() not in ('.zip', '.json') and payload.size > MAX_FILE:
        raise HTTPException(413, 'Arquivo textual excede 8 MiB; o limite por arquivo protege o processamento')
    with _lock(directory), _transaction(directory) as db:
        active = db.execute("SELECT count(*),coalesce(sum(size),0),coalesce(sum(staging_reservation),0) FROM migration_jobs WHERE owner_id=? AND state IN ('receiving','inventory','review','indexing','failed')", (owner['id'],)).fetchone()
        if active[0] >= 8 or active[1] + payload.size > MAX_OWNER_STAGING or active[2] + payload.size * 6 > MAX_OWNER_STAGE_DISK:
            raise HTTPException(409, 'Revise ou cancele migrações pendentes; quota de staging atingida')
        _space(directory, payload.size * 6)
        job = uuid.uuid4().hex
        stage = _stage(job, directory, create=True)
        fd = _open_private(stage / 'upload', os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        _sync_directory(stage)
        created = iso()
        expires = (datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)).isoformat()
        db.execute('INSERT INTO migration_jobs(id,owner_id,filename,size,sha256,source_kind,state,client_not_sent,staging_reservation,created_at,updated_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                   (job, owner['id'], name, payload.size, payload.sha256.lower(), payload.source_kind, 'receiving', payload.client_not_sent, payload.size * 6, created, created, expires))
    return get_job(job, owner, directory=directory)


def append_upload(job, offset, chunk, owner, directory=None):
    if not isinstance(offset, int) or offset < 0 or not chunk or len(chunk) > MAX_CHUNK:
        raise HTTPException(422, 'Bloco deve conter até 1 MiB e offset válido')
    with _lock(directory), _transaction(directory) as db:
        row = _owned(db, job, owner)
        if row['state'] != 'receiving':
            raise HTTPException(409, 'Upload já encerrado')
        if offset + len(chunk) > row['size']:
            raise HTTPException(413, 'Bloco excede o tamanho declarado')
        fd = _open_private(_stage(job, directory) / 'upload', os.O_RDWR)
        with os.fdopen(fd, 'r+b') as file:
            if offset < row['received']:
                file.seek(offset)
                if offset + len(chunk) <= row['received'] and file.read(len(chunk)) == chunk:
                    return {'id': job, 'state': row['state'], 'received': row['received'], 'size': row['size']}
                raise HTTPException(409, 'Bloco conflitante; confira o offset recebido')
            if offset != row['received']:
                raise HTTPException(409, 'Offset incorreto; retome a partir dos bytes recebidos')
            # A crash after fsync but before commit leaves extra bytes. Never
            # infer authorization/progress from file length: discard that tail.
            file.truncate(row['received'])
            file.seek(offset)
            file.write(chunk)
            file.flush()
            os.fsync(file.fileno())
        db.execute('UPDATE migration_jobs SET received=?,updated_at=? WHERE id=?', (offset + len(chunk), iso(), job))
    return {'id': job, 'state': 'receiving', 'received': offset + len(chunk), 'size': row['size']}


def finish_upload(job, owner, directory=None):
    with _lock(directory), _transaction(directory) as db:
        row = _owned(db, job, owner)
        if row['state'] != 'receiving':
            return get_job(job, owner, directory=directory)
        if row['received'] != row['size']:
            raise HTTPException(409, 'Upload incompleto; retome dos bytes recebidos')
        digest = hashlib.sha256()
        fd = _open_private(_stage(job, directory) / 'upload', os.O_RDWR)
        with os.fdopen(fd, 'r+b') as file:
            file.truncate(row['received'])
            for chunk in iter(lambda: file.read(MAX_CHUNK), b''):
                digest.update(chunk)
        if digest.hexdigest() != row['sha256']:
            raise HTTPException(422, 'Checksum não confere; cancele e envie o arquivo correto')
        db.execute("UPDATE migration_jobs SET state='inventory',updated_at=? WHERE id=?", (iso(), job))
    return get_job(job, owner, directory=directory)


def _report(db, job):
    counts = {r['category']: r['n'] for r in db.execute('SELECT category,count(*) n FROM migration_entries WHERE job_id=? GROUP BY category', (job,))}
    errors = db.execute("SELECT count(*) FROM migration_entries WHERE job_id=? AND status='error'", (job,)).fetchone()[0]
    states = {r['status']: r['n'] for r in db.execute('SELECT status,count(*) n FROM migration_items WHERE job_id=? GROUP BY status', (job,))}
    selected = db.execute('SELECT count(*) FROM migration_items WHERE job_id=? AND selected=1', (job,)).fetchone()[0]
    total = sum(states.values())
    report = dict(entries=dict(total=sum(counts.values()), directories=counts.get('directory', 0), ignored=counts.get('ignored', 0), eligible=counts.get('eligible', 0), errors=errors, processed=db.execute("SELECT count(*) FROM migration_entries WHERE job_id=? AND status!='pending'", (job,)).fetchone()[0]),
                  documents=dict(recognized=total, selected=selected, not_selected=total-selected, imported=states.get('imported', 0), duplicates=states.get('duplicate', 0), indexed=states.get('imported', 0)+states.get('duplicate', 0), errors=states.get('error', 0)),
                  ignored=[dict(r) for r in db.execute("SELECT path,reason FROM migration_entries WHERE job_id=? AND category='ignored' ORDER BY ordinal LIMIT 100", (job,))],
                  errors=[dict(r) for r in db.execute("SELECT path,reason FROM migration_entries WHERE job_id=? AND status='error' ORDER BY ordinal LIMIT 100", (job,))],
                  notes=['Importar e indexar não chama modelos.', 'ZIP bruto e textos em revisão ficam em staging privado; são removidos ao concluir ou cancelar.', 'Anexos e formatos ignorados não ficam disponíveis como fontes.'])
    # Flat aliases keep UI/report consumers simple, without mixing descriptors
    # with documents (one conversation export may produce many documents).
    report['omissions'] = {}
    for entry in db.execute('SELECT omissions_json FROM migration_entries WHERE job_id=?', (job,)):
        for key, count in json.loads(entry[0]).items():
            report['omissions'][key] = report['omissions'].get(key, 0) + count
    report.update({key: value for key, value in report['documents'].items() if key != 'errors'})
    report['document_errors'] = report['documents']['errors']
    report['eligible'] = report['entries']['eligible']
    report['ignored_total'] = report['entries']['ignored']
    report['available'] = db.execute("SELECT count(*) FROM migration_items i JOIN documents d ON d.id=i.document_id WHERE i.job_id=? AND i.selected=1 AND i.status IN ('imported','duplicate') AND d.active=1", (job,)).fetchone()[0]
    report['client_not_sent'] = db.execute('SELECT client_not_sent FROM migration_jobs WHERE id=?', (job,)).fetchone()[0]
    report['errors'] += [dict(r) for r in db.execute("SELECT path,error AS reason FROM migration_items WHERE job_id=? AND status='error' LIMIT 100", (job,))]
    report['errors_list_truncated'] = errors + states.get('error', 0) > len(report['errors'])
    report['ignored_list_truncated'] = report['ignored_total'] > len(report['ignored'])
    return report


def get_job(job, owner, offset=0, limit=100, q='', directory=None):
    offset, limit = max(0, int(offset)), min(100, max(1, int(limit)))
    with _connection(directory) as db:
        row = _owned(db, job, owner)
        result = dict(row)
        result.pop('owner_id')
        selection = json.loads(result.pop('selection_json'))
        result.update(selection=selection, selected_groups=selection['groups'], excluded_ids=selection['excluded_ids'])
        result.pop('report_json')
        result['report'] = _report(db, job)
        result['limits'] = limits()
        result['groups'] = [dict(r) for r in db.execute("SELECT group_name AS id,group_name AS name,count(*) AS total,sum(selected) AS selected,sum(status IN ('imported','duplicate')) AS indexed,sum(status='error') AS errors FROM migration_items WHERE job_id=? GROUP BY group_name ORDER BY group_name", (job,))]
        params = [job]
        where = 'job_id=?'
        if q:
            where += " AND (path LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\')"
            pattern = '%' + q[:200].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            params += [pattern, pattern]
        result['total'] = db.execute(f'SELECT count(*) FROM migration_items WHERE {where}', params).fetchone()[0]
        result['offset'] = offset
        result['items'] = []
        for r in db.execute(f'SELECT * FROM migration_items WHERE {where} ORDER BY path,id LIMIT ? OFFSET ?', params+[limit, offset]):
            item = dict(r)
            item.pop('job_id')
            item['group'] = item.pop('group_name')
            item['duplicates'] = [dict(r) for r in db.execute('SELECT id,title,area_id,active FROM documents WHERE owner_id=? AND hash=? LIMIT 20', (owner['id'], item['hash']))]
            item['conflicts'] = [dict(r) for r in db.execute('SELECT id,title,area_id,active FROM documents WHERE owner_id=? AND path=? AND hash!=? UNION SELECT d.id,d.title,d.area_id,d.active FROM documents d JOIN migration_provenance p ON p.document_id=d.id WHERE p.source_id=? AND d.owner_id=? AND d.hash!=? LIMIT 20', (owner['id'], item['path'], item['hash'], item['source_id'], owner['id'], item['hash']))]
            item['preview'] = ''
            staged = _stage(job, directory) / (item['id'] + '.json')
            if item['status'] == 'staged' and staged.is_file() and not staged.is_symlink():
                preview = staged.with_suffix('.preview')
                if preview.is_file() and not preview.is_symlink():
                    record = _read_record(preview)
                    item['preview'] = record['preview']
                    item['omissions'] = record.get('omissions', {})
            elif item['document_id']:
                content = db.execute('SELECT substr(content,1,600) FROM documents WHERE id=? AND owner_id=?', (item['document_id'], owner['id'])).fetchone()
                item['preview'] = content[0] if content else ''
            result['items'].append(item)
        result['usable'] = result['report']['available'] > 0
        result['selected_complete'] = row['state'] in ('completed', 'partial') and result['report']['documents']['selected'] == result['report']['documents']['indexed']
        result['coverage_complete'] = result['selected_complete'] and result['report']['entries']['errors'] == 0 and result['report']['documents']['errors'] == 0 and result['report']['entries']['ignored'] == 0 and result['report']['documents']['not_selected'] == 0 and not any(result['report']['omissions'].values())
        result['raw_retained'] = (_stage(job, directory) / 'upload').is_file()
    return result


def list_jobs(owner, directory=None):
    with _connection(directory) as db:
        jobs = [r[0] for r in db.execute('SELECT id FROM migration_jobs WHERE owner_id=? ORDER BY created_at DESC LIMIT 100', (owner['id'],))]
    return [get_job(job, owner, limit=1, directory=directory) for job in jobs]


def _selection(db, job, payload):
    groups, excluded = sorted(set(payload.groups)), sorted(set(payload.excluded_ids))
    available = {r[0] for r in db.execute('SELECT DISTINCT group_name FROM migration_items WHERE job_id=?', (job,))}
    if not set(groups) <= available | {'*'}:
        raise HTTPException(422, 'Grupo não pertence a esta migração')
    ids = {r[0] for r in db.execute('SELECT id FROM migration_items WHERE job_id=?', (job,))}
    if not set(excluded) <= ids:
        raise HTTPException(422, 'Exceção não pertence a esta migração')
    return dict(groups=groups, excluded_ids=excluded)


def save_selection(job, payload, owner, directory=None):
    with _lock(directory), _transaction(directory) as db:
        row = _owned(db, job, owner)
        if row['state'] != 'review':
            raise HTTPException(409, 'Seleção disponível quando o inventário aguarda revisão')
        selection = _selection(db, job, payload)
        db.execute('UPDATE migration_jobs SET selection_json=?,updated_at=? WHERE id=?', (json.dumps(selection), iso(), job))
    return get_job(job, owner, directory=directory)


def confirm(job, payload, owner, audit=None, directory=None):
    with _lock(directory), _transaction(directory) as db:
        row = _owned(db, job, owner)
        selection = _selection(db, job, payload)
        if row['state'] in ('indexing', 'completed', 'partial'):
            if selection != json.loads(row['selection_json']) or (payload.area_id and payload.area_id != row['area_id']):
                raise HTTPException(409, 'Esta migração já foi autorizada com outra seleção')
        elif row['state'] == 'review':
            area = db.execute('SELECT id FROM areas WHERE owner_id=?' + (' AND id=?' if payload.area_id else ' ORDER BY created_at,id LIMIT 1'), [owner['id']] + ([payload.area_id] if payload.area_id else [])).fetchone()
            if not area:
                raise HTTPException(404, 'Área de autorização não encontrada')
            groups, excluded = set(selection['groups']), set(selection['excluded_ids'])
            selected = []
            for item in db.execute('SELECT id,group_name FROM migration_items WHERE job_id=?', (job,)):
                if ('*' in groups or item['group_name'] in groups) and item['id'] not in excluded:
                    selected.append((item['id'],))
            if not selected:
                raise HTTPException(422, 'Escolha ao menos um grupo ou documento')
            db.executemany('UPDATE migration_items SET selected=1 WHERE id=?', selected)
            size = db.execute('SELECT coalesce(sum(bytes),0) FROM migration_items WHERE job_id=? AND selected=1', (job,)).fetchone()[0]
            storage = db.execute('SELECT document_bytes,document_count FROM migration_storage WHERE owner_id=?', (owner['id'],)).fetchone()
            existing_bytes, existing_count = tuple(storage) if storage else (0, 0)
            reservations = db.execute("SELECT coalesce(sum(i.bytes),0),count(*) FROM migration_items i JOIN migration_jobs j ON j.id=i.job_id WHERE j.owner_id=? AND j.id!=? AND j.state='indexing' AND i.selected=1 AND i.status='staged'", (owner['id'], job)).fetchone()
            if size + existing_bytes + reservations[0] > MAX_OWNER_TEXT:
                raise HTTPException(409, 'Quota da biblioteca atingida; remova materiais antes de autorizar')
            if len(selected) + existing_count + reservations[1] > MAX_OWNER_DOCUMENTS:
                raise HTTPException(409, 'Quota de documentos da biblioteca atingida')
            _space(directory, size * 5)
            db.execute('INSERT INTO imports(id,owner_id,area_id,name,state,report_json,created_at) VALUES(?,?,?,?,?,?,?)', (job, owner['id'], area['id'], row['filename'], 'indexing', '{}', iso()))
            db.execute("UPDATE migration_jobs SET state='indexing',area_id=?,selection_json=?,updated_at=? WHERE id=?", (area['id'], json.dumps(selection), iso(), job))
            if audit:
                audit(db, owner['id'], 'migration.authorized', 'migration', job, {'selected': len(selected)})
        else:
            raise HTTPException(409, 'Migração não aguarda revisão')
    return get_job(job, owner, directory=directory)


def _cleanup(job, directory=None):
    stage = _stage(job, directory)
    if stage.exists():
        shutil.rmtree(stage)
        _sync_directory(stage.parent)


def cancel(job, owner, audit=None, directory=None):
    with _lock(directory), _transaction(directory) as db:
        row = _owned(db, job, owner)
        if row['state'] in ('completed', 'partial'):
            raise HTTPException(409, 'Migração concluída; use remover para desfazer o lote')
        db.execute("UPDATE migration_jobs SET state='cancelled',updated_at=? WHERE id=?", (iso(), job))
        db.execute("UPDATE imports SET state='cancelled',report_json=? WHERE id=?", (json.dumps(_report(db, job)), job))
        if audit and row['state'] != 'cancelled':
            audit(db, owner['id'], 'migration.cancelled', 'migration', job, {'indexed': _report(db, job)['indexed']})
    _cleanup(job, directory)
    return get_job(job, owner, directory=directory)


def remove(job, owner, audit=None, directory=None):
    with _lock(directory), _transaction(directory) as db:
        _owned(db, job, owner)
        docs = [r[0] for r in db.execute('SELECT DISTINCT document_id FROM document_imports WHERE import_id=?', (job,))]
        db.execute('INSERT OR IGNORE INTO migration_cleanup VALUES(?)', (job,))
        db.execute('DELETE FROM imports WHERE id=? AND owner_id=?', (job, owner['id']))
        db.execute('DELETE FROM migration_jobs WHERE id=? AND owner_id=?', (job, owner['id']))
        for doc in docs:
            if not db.execute('SELECT 1 FROM document_imports WHERE document_id=?', (doc,)).fetchone():
                db.execute('DELETE FROM documents WHERE id=? AND owner_id=?', (doc, owner['id']))
        if audit:
            audit(db, owner['id'], 'migration.removed', 'migration', job)
    try:
        _cleanup(job, directory)
    except OSError as error:
        raise HTTPException(503, 'Fontes removidas da biblioteca; exclusão do staging privado pendente. Confira espaço e permissões.') from error
    with _transaction(directory) as db:
        db.execute('DELETE FROM migration_cleanup WHERE job_id=?', (job,))
    return {'ok': True}


def _zip_directory_guard(path):
    """Bound the central directory before ZipFile allocates its descriptors."""
    fd = _open_private(path, os.O_RDONLY)
    with os.fdopen(fd, 'rb') as file:
        size = file.seek(0, os.SEEK_END)
        file.seek(max(0, size - 65_557))
        tail = file.read(65_557)
    position = tail.rfind(b'PK\x05\x06')
    while position >= 0:
        if position + 22 <= len(tail):
            values = struct.unpack_from('<4s4H2IH', tail, position)
            if position + 22 + values[7] == len(tail):
                break
        position = tail.rfind(b'PK\x05\x06', 0, position)
    if position < 0:
        raise ValueError('ZIP inválido; diretório central ausente')
    _, disk, central_disk, disk_entries, entries, central_bytes, central_offset, _ = values
    if entries == 0xffff or central_bytes == 0xffffffff or central_offset == 0xffffffff:
        raise ValueError('ZIP64 não suportado neste adaptador; use ZIP com até 50.000 entradas')
    if disk or central_disk or disk_entries != entries:
        raise ValueError('ZIP multipartes não suportado')
    if entries > MAX_DESCRIPTORS or central_bytes > MAX_CENTRAL_BYTES:
        raise ValueError('ZIP excede quota de descritores ou metadados do diretório central')
    if central_offset + central_bytes > size:
        raise ValueError('Diretório central do ZIP inválido')


def _catalogue(row, directory):
    entries = []
    expanded = eligible = 0
    if row['filename'].lower().endswith('.zip'):
        _zip_directory_guard(_stage(row['id'], directory) / 'upload')
        with zipfile.ZipFile(_stage(row['id'], directory) / 'upload') as archive:
            infos = archive.infolist()
            if len(infos) > MAX_DESCRIPTORS:
                raise ValueError('ZIP excede a quota de 50.000 descritores, incluindo pastas e metadados')
            paths = set()
            for ordinal, info in enumerate(infos):
                path = _safe_path(info.orig_filename)
                if path in paths:
                    raise ValueError('ZIP contém caminhos repetidos; resolva o conflito antes de importar')
                paths.add(path)
                mode = stat.S_IFMT(info.external_attr >> 16)
                if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or info.flag_bits & 1:
                    raise ValueError('ZIP com link simbólico ou criptografia não suportado')
                if info.file_size > max(info.compress_size, 1) * 200:
                    raise ValueError('Razão de expansão excede a proteção contra ZIP bomb')
                expanded += info.file_size
                category, reason = _category(path, info.is_dir())
                if category == 'eligible':
                    eligible += info.file_size
                    per_file_limit = MAX_UPLOAD if PurePosixPath(path).suffix.lower() == '.json' else MAX_FILE
                    if info.file_size > per_file_limit:
                        category, reason = 'eligible', ('Exportação JSON excede 100 MiB' if PurePosixPath(path).suffix.lower() == '.json' else 'Arquivo textual excede 8 MiB')
                entries.append((row['id'], ordinal, path, info.file_size, category, 'error' if category == 'eligible' and reason else ('pending' if category == 'eligible' else 'done'), reason))
    else:
        category, reason = _category(row['filename'])
        entries = [(row['id'], 0, row['filename'], row['size'], category, 'pending', reason)]
        expanded = eligible = row['size']
    if expanded > MAX_EXPANDED or eligible > MAX_TEXT_TOTAL:
        raise ValueError('ZIP excede quota de expansão (1 GiB total ou 500 MiB de texto elegível)')
    _space(directory, eligible * 6)
    with _transaction(directory) as db:
        current = db.execute('SELECT state,catalogued FROM migration_jobs WHERE id=?', (row['id'],)).fetchone()
        if not current or current['state'] != 'inventory' or current['catalogued']:
            return
        others = db.execute("SELECT coalesce(sum(staging_reservation),0) FROM migration_jobs WHERE owner_id=? AND id!=? AND state IN ('receiving','inventory','review','indexing','failed')", (row['owner_id'], row['id'])).fetchone()[0]
        reservation = row['size'] + eligible * 4
        if others + reservation > MAX_OWNER_STAGE_DISK:
            raise ValueError('Quota de disco reservado para staging atingida; revise ou cancele outros lotes')
        db.executemany('INSERT INTO migration_entries(job_id,ordinal,path,bytes,category,status,reason) VALUES(?,?,?,?,?,?,?)', entries)
        db.execute('UPDATE migration_jobs SET catalogued=1,staging_reservation=?,updated_at=? WHERE id=?', (reservation, iso(), row['id']))


def _group(path, kind):
    if kind in ('chatgpt', 'claude'):
        return 'ChatGPT' if kind == 'chatgpt' else 'Claude'
    parent = str(PurePosixPath(path).parent)
    return parent


def _write_record(path, record):
    temporary = path.with_suffix('.pending')
    fd = _open_private(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
    with os.fdopen(fd, 'w', encoding='utf-8') as file:
        json.dump(record, file, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)
    _sync_directory(path.parent)


def _read_record(path):
    fd = _open_private(path, os.O_RDONLY)
    with os.fdopen(fd, 'r', encoding='utf-8') as file:
        return json.load(file)


def _inventory_slice(row, directory, batch_size=8):
    if not row['catalogued']:
        _catalogue(row, directory)
    with _connection(directory) as db:
        entries = list(db.execute("SELECT * FROM migration_entries WHERE job_id=? AND status='pending' ORDER BY ordinal LIMIT ?", (row['id'], batch_size)))
    archive = zipfile.ZipFile(_stage(row['id'], directory) / 'upload') if row['filename'].lower().endswith('.zip') else None
    try:
        for entry in entries:
            staged = []
            try:
                source = archive.open(archive.infolist()[entry['ordinal']]) if archive else os.fdopen(_open_private(_stage(row['id'], directory) / 'upload', os.O_RDONLY), 'rb')
                omissions = {}
                with source:
                    for record in iter_entry(entry['path'], source):
                        digest = hashlib.sha256(record['content'].encode()).hexdigest()
                        item = uuid.uuid5(uuid.UUID(hex=row['id']), entry['path'] + '\x00' + record['source_id'] + '\x00' + digest).hex
                        path = entry['path'] if record['kind'] in ('markdown', 'text') else entry['path'] + '#' + record['source_id']
                        _write_record(_stage(row['id'], directory) / (item + '.json'), record)
                        _write_record(_stage(row['id'], directory) / (item + '.preview'), {'preview': record['content'][:600], 'omissions': record.get('metadata', {}).get('omissions', {})})
                        staged.append((item, row['id'], path, record['title'], record['kind'], record['source_id'], _group(entry['path'], record['kind']), digest, len(record['content']), len(record['content'].encode())))
                        for key, count in record.get('metadata', {}).get('omissions', {}).items():
                            omissions[key] = omissions.get(key, 0) + count
                with _transaction(directory) as db:
                    current = db.execute('SELECT state FROM migration_jobs WHERE id=?', (row['id'],)).fetchone()
                    if not current or current[0] != 'inventory':
                        return
                    count = db.execute('SELECT count(*) FROM migration_items WHERE job_id=?', (row['id'],)).fetchone()[0]
                    if count + len(staged) > MAX_DOCUMENTS:
                        raise ValueError('Migração excede 50.000 documentos reconhecidos')
                    text_size = db.execute('SELECT coalesce(sum(bytes),0) FROM migration_items WHERE job_id=?', (row['id'],)).fetchone()[0]
                    if text_size + sum(item[9] for item in staged) > MAX_TEXT_TOTAL:
                        raise ValueError('Migração excede quota de 500 MiB de texto normalizado')
                    db.executemany('INSERT OR IGNORE INTO migration_items(id,job_id,path,title,kind,source_id,group_name,hash,characters,bytes) VALUES(?,?,?,?,?,?,?,?,?,?)', staged)
                    db.execute("UPDATE migration_entries SET status='done',omissions_json=? WHERE job_id=? AND ordinal=?", (json.dumps(omissions), row['id'], entry['ordinal']))
                    db.execute('UPDATE migration_jobs SET updated_at=? WHERE id=?', (iso(), row['id']))
            except (ValueError, UnicodeError, TypeError, KeyError, AttributeError, zipfile.BadZipFile, RuntimeError, NotImplementedError, RecursionError) as error:
                for item in staged:
                    (_stage(row['id'], directory) / (item[0] + '.json')).unlink(missing_ok=True)
                    (_stage(row['id'], directory) / (item[0] + '.preview')).unlink(missing_ok=True)
                with _transaction(directory) as db:
                    db.execute("UPDATE migration_entries SET status='error',reason=? WHERE job_id=? AND ordinal=? AND EXISTS(SELECT 1 FROM migration_jobs WHERE id=? AND state='inventory')", (str(error)[:300], row['id'], entry['ordinal'], row['id']))
    finally:
        if archive:
            archive.close()
    with _transaction(directory) as db:
        pending = db.execute("SELECT count(*) FROM migration_entries WHERE job_id=? AND status='pending'", (row['id'],)).fetchone()[0]
        if not pending:
            count = db.execute('SELECT count(*) FROM migration_items WHERE job_id=?', (row['id'],)).fetchone()[0]
            db.execute("UPDATE migration_jobs SET state=?,error=?,updated_at=? WHERE id=? AND state='inventory'", ('review' if count else 'failed', None if count else 'Nenhum documento reconhecido; confira os erros e formatos ignorados.', iso(), row['id']))


def _index_slice(row, directory, batch_size=20):
    with _connection(directory) as db:
        items = list(db.execute("SELECT * FROM migration_items WHERE job_id=? AND selected=1 AND status='staged' ORDER BY path,id LIMIT ?", (row['id'], batch_size)))
    if items and not _stage(row['id'], directory).is_dir():
        raise FileNotFoundError('Staging indisponível após restauração')
    for item in items:
        try:
            record = _read_record(_stage(row['id'], directory) / (item['id'] + '.json'))
            if hashlib.sha256(record['content'].encode()).hexdigest() != item['hash']:
                raise ValueError('Conteúdo de staging não confere com o inventário')
            with _transaction(directory) as db:
                current = db.execute('SELECT state FROM migration_jobs WHERE id=?', (row['id'],)).fetchone()
                checkpoint = db.execute('SELECT status,selected FROM migration_items WHERE id=?', (item['id'],)).fetchone()
                if not current or current[0] != 'indexing':
                    return
                if checkpoint[0] != 'staged' or not checkpoint[1]:
                    continue
                existing = db.execute('SELECT id FROM documents WHERE owner_id=? AND area_id=? AND hash=?', (row['owner_id'], row['area_id'], item['hash'])).fetchone()
                if existing:
                    document, status = existing[0], 'duplicate'
                else:
                    document, status = str(uuid.uuid4()), 'imported'
                    storage = db.execute('SELECT document_bytes,document_count FROM migration_storage WHERE owner_id=?', (row['owner_id'],)).fetchone()
                    if storage and (storage[0] + item['bytes'] > MAX_OWNER_TEXT or storage[1] >= MAX_OWNER_DOCUMENTS):
                        raise ValueError('Quota da biblioteca mudou durante a indexação; fonte não publicada')
                    db.execute('INSERT INTO documents(id,owner_id,area_id,title,path,kind,content,hash,created_at) VALUES(?,?,?,?,?,?,?,?,?)', (document, row['owner_id'], row['area_id'], item['title'], item['path'], item['kind'], record['content'], item['hash'], iso()))
                    chunks = chunk_content(record['content'], kind=record['kind'], messages=record.get('metadata', {}).get('messages') if record['kind'] in ('chatgpt', 'claude') else None)
                    db.executemany('INSERT INTO chunks(document_id,ordinal,content,searchable) VALUES(?,?,?,?)', ((document, n, chunk, normalized(chunk)) for n, chunk in enumerate(chunks)))
                db.execute('INSERT OR IGNORE INTO document_imports VALUES(?,?,?)', (document, row['id'], item['path']))
                db.execute('INSERT OR IGNORE INTO migration_provenance VALUES(?,?,?,?,?)', (document, row['id'], item['id'], item['source_id'], json.dumps(record.get('metadata', {}), ensure_ascii=False)))
                db.execute('UPDATE migration_items SET status=?,document_id=? WHERE id=?', (status, document, item['id']))
                db.execute('UPDATE migration_jobs SET updated_at=? WHERE id=?', (iso(), row['id']))
        except (ValueError, UnicodeError, FileNotFoundError) as error:
            with _transaction(directory) as db:
                db.execute("UPDATE migration_items SET status='error',error=? WHERE id=? AND EXISTS(SELECT 1 FROM migration_jobs WHERE id=? AND state='indexing')", (str(error)[:200], item['id'], row['id']))
    completed = False
    with _transaction(directory) as db:
        pending = db.execute("SELECT count(*) FROM migration_items WHERE job_id=? AND selected=1 AND status='staged'", (row['id'],)).fetchone()[0]
        current = db.execute('SELECT state FROM migration_jobs WHERE id=?', (row['id'],)).fetchone()
        if not pending and current and current[0] == 'indexing':
            _complete_index(db, row['id'])
            completed = True
    if completed:
        _cleanup(row['id'], directory)


def process_next(directory=None):
    """One checkpointed slice; safe to call after restart, never retries a model."""
    directory = _directory(directory)
    with _lock(directory), _connection(directory) as db:
        # Also serialize workers in separate processes. API publication itself
        # checks current authorization inside its SQLite write transaction.
        lock_fd = _open_private(directory / '.migration-worker.lock', os.O_CREAT | os.O_RDWR)
        try:
            try:
                import fcntl
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            except ImportError:
                pass  # Windows distribution is not an advertised pilot path.
            row = db.execute("SELECT * FROM migration_jobs WHERE state IN ('inventory','indexing') ORDER BY updated_at,id LIMIT 1").fetchone()
            if not row:
                return False
            try:
                if row['state'] == 'inventory':
                    _inventory_slice(row, directory)
                else:
                    _index_slice(row, directory)
            except (ValueError, zipfile.BadZipFile, OSError, HTTPException, sqlite3.DatabaseError) as error:
                message = error.detail if isinstance(error, HTTPException) else str(error)
                if isinstance(error, FileNotFoundError):
                    message = 'Staging não está disponível nesta instalação restaurada. Fontes já aprovadas foram preservadas; envie o arquivo novamente em uma nova migração.'
                with _transaction(directory) as update:
                    update.execute("UPDATE migration_jobs SET state='failed',error=?,retryable=?,updated_at=? WHERE id=? AND state IN ('inventory','indexing')", (str(message)[:300], int(isinstance(error, (OSError, sqlite3.OperationalError)) and not isinstance(error, FileNotFoundError)), iso(), row['id']))
            return True
        finally:
            os.close(lock_fd)


def resume(job, owner, directory=None):
    with _lock(directory), _transaction(directory) as db:
        row = _owned(db, job, owner)
        if row['state'] != 'failed' or not row['retryable']:
            raise HTTPException(409, 'Esta falha exige novo envio ou revisão; não pode ser retomada')
        state = 'indexing' if row['area_id'] else 'inventory'
        db.execute('UPDATE migration_jobs SET state=?,error=NULL,retryable=0,updated_at=? WHERE id=?', (state, iso(), job))
    return get_job(job, owner, directory=directory)


def expire_staging(directory=None):
    directory = _directory(directory)
    with _lock(directory), _transaction(directory) as db:
        expired = [r[0] for r in db.execute("SELECT id FROM migration_jobs WHERE state IN ('receiving','review','failed') AND expires_at<?", (iso(),))]
        for job in expired:
            db.execute("UPDATE migration_jobs SET state='cancelled',error='Staging expirou após sete dias. Envie novamente para continuar.',updated_at=? WHERE id=?", (iso(), job))
            _cleanup(job, directory)
        # Completing the DB checkpoint and deleting files are independent. A
        # restart cleans a terminal job whose cleanup was interrupted.
        for row in db.execute("SELECT id FROM migration_jobs WHERE state IN ('completed','partial','cancelled')"):
            _cleanup(row['id'], directory)
        for row in list(db.execute('SELECT job_id FROM migration_cleanup')):
            _cleanup(row[0], directory)
            db.execute('DELETE FROM migration_cleanup WHERE job_id=?', (row[0],))


async def worker(stop, directory=None):
    directory = _directory(directory)
    initialize(directory)
    try:
        await asyncio.to_thread(expire_staging, directory)
    except Exception:
        logging.getLogger(__name__).exception('Staging cleanup pending; worker continues with durable jobs')
    while not stop.is_set():
        try:
            did_work = await asyncio.to_thread(process_next, directory)
            if not did_work:
                await asyncio.to_thread(expire_staging, directory)
        except Exception:
            logging.getLogger(__name__).exception('Migration worker failed; durable checkpoints preserved')
            did_work = False
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.05 if did_work else 1)
        except asyncio.TimeoutError:
            pass
