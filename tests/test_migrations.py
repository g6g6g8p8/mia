"""Durability and authorization boundaries of the local migration engine."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import stat
import struct
import zipfile

import pytest
from fastapi import HTTPException

from mia import db, migrations as m


@pytest.fixture
def installation(tmp_path, monkeypatch):
    monkeypatch.setenv('MIA_DATA_DIR', str(tmp_path))
    db.initialize()
    m.initialize(tmp_path)
    with db.transaction(immediate=True) as connection:
        connection.execute('INSERT INTO owner VALUES(1,?,?,?,?,?)', ('Synthetic owner', '', 'UTC', 'not-a-password', '2030-01-01'))
        connection.execute('INSERT INTO areas VALUES(?,?,?,?,?,?,?)', ('projects', 1, 'Projects', '', 'slate', '2030-01-01', '2030-01-01'))
    return tmp_path, {'id': 1}


def archive(entries, compression=zipfile.ZIP_STORED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=compression) as output:
        for path, text in entries:
            output.writestr(path, text)
    return buffer.getvalue()


def received(installation, raw, filename='vault.zip'):
    directory, owner = installation
    job = m.create_upload(m.CreateUpload(filename=filename, size=len(raw), sha256=hashlib.sha256(raw).hexdigest()), owner, directory)
    for offset in range(0, len(raw), m.MAX_CHUNK):
        m.append_upload(job['id'], offset, raw[offset:offset + m.MAX_CHUNK], owner, directory)
    m.finish_upload(job['id'], owner, directory)
    return job['id']


def drain(installation, job, states=('review',)):
    directory, owner = installation
    for _ in range(1000):
        with m._connection(directory) as connection:
            state = connection.execute('SELECT state FROM migration_jobs WHERE id=?', (job,)).fetchone()[0]
        if state in states:
            return m.get_job(job, owner, directory=directory)
        assert state not in ('failed', 'cancelled'), m.get_job(job, owner, directory=directory)
        assert m.process_next(directory)
    pytest.fail('Migration did not reach its checkpointed terminal state')


def counts(directory):
    with m._connection(directory) as connection:
        return tuple(connection.execute('SELECT count(*) FROM ' + name).fetchone()[0] for name in ('documents', 'chunks', 'document_imports', 'migration_provenance'))


def test_1500_note_vault_filters_descriptors_groups_then_publishes_without_splitting(installation):
    directory, owner = installation
    entries = [(f'Vault/Projects/{i % 15:02}/note-{i:04}.md', f'# Note {i}\nUnique decision number {i}.') for i in range(1500)]
    entries += [('Vault/', ''), ('Vault/.obsidian/settings.json', '{}'), ('Vault/.git/config', 'metadata'), ('Vault/__MACOSX/._note', 'metadata'), ('Vault/image.png', b'not text')]
    raw = archive(entries)
    initial_digest = hashlib.sha256(raw).hexdigest()
    job = received(installation, raw)
    review = drain(installation, job)
    assert review['report']['entries'] == {'total': 1505, 'directories': 1, 'ignored': 4, 'eligible': 1500, 'errors': 0, 'processed': 1505}
    assert review['report']['recognized'] == 1500
    assert len(review['items']) == 100 and review['total'] == 1500
    assert len(review['groups']) == 15
    assert counts(directory) == (0, 0, 0, 0)
    selection = m.Confirm(groups=['*'])
    m.confirm(job, selection, owner, directory=directory)
    done = drain(installation, job, ('completed', 'partial'))
    assert done['state'] == 'completed'
    assert done['selected_complete'] is True
    assert done['coverage_complete'] is False  # Ignored resources remain explicit.
    assert done['report']['imported'] == done['report']['indexed'] == 1500
    assert counts(directory) == (1500, 1500, 1500, 1500)
    assert not m._stage(job, directory).exists()
    assert hashlib.sha256(raw).hexdigest() == initial_digest
    assert m.confirm(job, selection, owner, directory=directory)['report']['indexed'] == 1500


def test_upload_retransmission_offset_checksum_and_crash_tail_are_safe(installation):
    directory, owner = installation
    raw = b'# Long enough\nOriginal source text preserved.'
    job = m.create_upload(m.CreateUpload(filename='note.md', size=len(raw), sha256=hashlib.sha256(raw).hexdigest()), owner, directory)['id']
    assert m.append_upload(job, 0, raw[:10], owner, directory)['received'] == 10
    assert m.append_upload(job, 0, raw[:10], owner, directory)['received'] == 10
    with pytest.raises(HTTPException) as error:
        m.append_upload(job, 0, b'conflicting', owner, directory)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException):
        m.append_upload(job, 11, raw[11:], owner, directory)
    with pytest.raises(HTTPException):
        m.finish_upload(job, owner, directory)
    # Simulate fsync succeeding before the upload checkpoint committed.
    with (m._stage(job, directory) / 'upload').open('ab') as file:
        file.write(b'uncommitted disk bytes')
    m.initialize(directory)  # Restart does not invent progress from disk length.
    assert m.get_job(job, owner, directory=directory)['received'] == 10
    m.append_upload(job, 10, raw[10:], owner, directory)
    assert (m._stage(job, directory) / 'upload').read_bytes() == raw
    assert m.finish_upload(job, owner, directory)['state'] == 'inventory'
    assert m.finish_upload(job, owner, directory)['state'] == 'inventory'
    assert drain(installation, job)['items'][0]['preview'] == raw.decode()


def test_checksum_mismatch_never_reaches_inventory(installation):
    directory, owner = installation
    raw = b'# Wrong transfer\nKeep private.'
    job = m.create_upload(m.CreateUpload(filename='note.md', size=len(raw), sha256='0' * 64), owner, directory)['id']
    m.append_upload(job, 0, raw, owner, directory)
    with pytest.raises(HTTPException, match='Checksum'):
        m.finish_upload(job, owner, directory)
    assert m.get_job(job, owner, directory=directory)['state'] == 'receiving'
    assert counts(directory) == (0, 0, 0, 0)


def test_checkpoint_recovery_selection_exceptions_and_searchable_late_text(installation):
    directory, owner = installation
    long_text = '# History\n' + ('Earlier background only. ' * 11_000) + '\n\nLATE_DECISION_2030: choose the blue route.'
    raw = archive([(f'Projects/{i:02}.md', long_text + str(i)) for i in range(32)] + [('Archive/private.md', 'DO_NOT_AUTHORIZE')])
    job = received(installation, raw)
    assert m.process_next(directory)  # Partial inventory commits one slice.
    m.initialize(directory)
    review = drain(installation, job)
    exception = next(item['id'] for item in review['items'] if item['path'] == 'Projects/01.md')
    selected = m.Selection(groups=['Projects'], excluded_ids=[exception])
    m.save_selection(job, selected, owner, directory)
    m.initialize(directory)
    assert m.get_job(job, owner, directory=directory)['selection'] == selected.model_dump()
    authorization = m.Confirm(**selected.model_dump())
    m.confirm(job, authorization, owner, directory=directory)
    assert m.process_next(directory)
    assert counts(directory)[0] == 20  # Useful sources exist before completion.
    m.initialize(directory)
    done = drain(installation, job, ('completed', 'partial'))
    assert done['report']['indexed'] == 31
    assert done['report']['not_selected'] == 2
    with m._connection(directory) as connection:
        assert connection.execute("SELECT count(*) FROM chunks WHERE content LIKE '%LATE_DECISION_2030%'").fetchone()[0] == 31
        assert not connection.execute("SELECT 1 FROM documents WHERE content LIKE '%DO_NOT_AUTHORIZE%'").fetchone()
        assert not connection.execute("SELECT 1 FROM documents WHERE path='Projects/01.md'").fetchone()
    with pytest.raises(HTTPException) as error:
        m.confirm(job, m.Confirm(groups=['*']), owner, directory=directory)
    assert error.value.status_code == 409


def test_cancellation_preserves_published_effects_and_undo_keeps_shared_sources(installation):
    directory, owner = installation
    raw = archive([(f'work/{i:02}.md', f'# Work {i}\nShared independent source {i}') for i in range(32)])
    job = received(installation, raw)
    drain(installation, job)
    m.confirm(job, m.Confirm(), owner, directory=directory)
    m.process_next(directory)
    assert counts(directory)[0] == 20
    cancelled = m.cancel(job, owner, directory=directory)
    assert cancelled['state'] == 'cancelled'
    assert cancelled['report']['indexed'] == 20
    assert not m.process_next(directory)
    assert counts(directory)[0] == 20
    assert not m._stage(job, directory).exists()
    second = received(installation, raw)
    drain(installation, second)
    m.confirm(second, m.Confirm(), owner, directory=directory)
    done = drain(installation, second, ('completed',))
    assert done['report']['duplicates'] == 20
    assert done['report']['imported'] == 12
    m.remove(job, owner, directory=directory)
    assert counts(directory)[0] == 32
    m.remove(second, owner, directory=directory)
    assert counts(directory) == (0, 0, 0, 0)


def test_owner_scope_paths_groups_and_foreign_area_are_enforced(installation):
    directory, owner = installation
    job = received(installation, archive([('work/one.md', 'Private'), ('work/two.md', 'Private 2')]))
    review = drain(installation, job)
    wrong_owner = {'id': 999}
    for action in (lambda: m.get_job(job, wrong_owner, directory=directory), lambda: m.cancel(job, wrong_owner, directory=directory), lambda: m.remove(job, wrong_owner, directory=directory), lambda: m.append_upload(job, 0, b'x', wrong_owner, directory)):
        with pytest.raises(HTTPException) as error:
            action()
        assert error.value.status_code == 404
    assert m.list_jobs(wrong_owner, directory) == []
    for selection in (m.Confirm(groups=['not-a-group']), m.Confirm(excluded_ids=['not-an-item']), m.Confirm(area_id='not-my-area')):
        with pytest.raises(HTTPException):
            m.confirm(job, selection, owner, directory=directory)
    assert counts(directory) == (0, 0, 0, 0)
    assert len(review['items']) == 2


@pytest.mark.parametrize('unsafe', ['../escape.md', '/absolute.md', 'folder\\escape.md', 'C:escape.md', '/'.join(['deep'] * 33) + '/note.md'])
def test_unsafe_zip_fails_before_inventory_or_publication(installation, unsafe):
    directory, owner = installation
    job = received(installation, archive([(unsafe, 'Unsafe input'), ('good.md', 'Good text')]))
    assert m.process_next(directory)
    failed = m.get_job(job, owner, directory=directory)
    assert failed['state'] == 'failed' and not failed['retryable']
    assert failed['report']['recognized'] == 0
    assert counts(directory) == (0, 0, 0, 0)


def test_symlink_zipbomb_encryption_and_descriptor_guard_are_separate(installation, monkeypatch):
    directory, owner = installation
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as output:
        info = zipfile.ZipInfo('link.md')
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        output.writestr(info, 'target')
    inputs = [buffer.getvalue(), archive([('bomb.md', b'0' * 100_000)], zipfile.ZIP_DEFLATED)]
    encrypted = bytearray(archive([('note.md', 'secret')]))
    central = encrypted.index(b'PK\x01\x02')
    struct.pack_into('<H', encrypted, central + 8, 1)
    inputs.append(bytes(encrypted))
    for raw in inputs:
        job = received(installation, raw)
        m.process_next(directory)
        assert m.get_job(job, owner, directory=directory)['state'] == 'failed'
        m.cancel(job, owner, directory=directory)
    monkeypatch.setattr(m, 'MAX_DESCRIPTORS', 2)
    job = received(installation, archive([('one.md', 'one'), ('two.md', 'two'), ('three.md', 'three')]))
    m.process_next(directory)
    assert m.get_job(job, owner, directory=directory)['state'] == 'failed'
    assert counts(directory) == (0, 0, 0, 0)


def test_partial_reports_reconcile_invalid_utf8_and_recognized_export_documents(installation):
    directory, owner = installation
    conversation = lambda i: {'uuid': str(i), 'name': 'Old conversation', 'chat_messages': [{'uuid': 'u-' + str(i), 'sender': 'human', 'created_at': '2020-01-01', 'text': 'My words'}, {'uuid': 'a-' + str(i), 'sender': 'assistant', 'text': 'Old AI hypothesis', 'attachments': [{'id': 'not-retained'}]}]}
    job = received(installation, archive([('readable.md', '# Valid\nContext'), ('broken.txt', b'\xff'), ('exports/claude.json', json.dumps([conversation(1), conversation(2)])), ('native.gdoc', '{}')]))
    review = drain(installation, job)
    assert review['report']['entries']['eligible'] == 3
    assert review['report']['recognized'] == 3  # 2 conversations + 1 note.
    assert review['report']['entries']['errors'] == 1
    assert review['report']['omissions']['attachments'] == 2
    assert 'Google' in review['report']['ignored'][0]['reason']
    m.confirm(job, m.Confirm(), owner, directory=directory)
    done = drain(installation, job, ('partial',))
    assert not done['coverage_complete']
    assert done['report']['indexed'] == 3
    with m._connection(directory) as connection:
        preserved = [json.loads(r[0]) for r in connection.execute("SELECT metadata_json FROM migration_provenance WHERE source_id LIKE 'claude:%'")]
    assert all([message['role'] for message in meta['messages']] == ['user', 'assistant'] for meta in preserved)
    assert all('not-retained' not in json.dumps(meta) for meta in preserved)


def test_staging_not_sqlite_content_and_expiration_or_restoration_is_truthful(installation):
    directory, owner = installation
    raw = b'# Sensitive synthetic material\nREVIEW_ONLY_NOT_IN_BACKUP'
    job = received(installation, raw, 'note.md')
    drain(installation, job)
    with m._connection(directory) as connection:
        tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0].startswith('migration_')]
        assert 'REVIEW_ONLY_NOT_IN_BACKUP' not in ''.join(str(tuple(r)) for table in tables for r in connection.execute('SELECT * FROM ' + table))
        connection.execute("UPDATE migration_jobs SET expires_at='2000-01-01' WHERE id=?", (job,))
    m.expire_staging(directory)
    assert m.get_job(job, owner, directory=directory)['state'] == 'cancelled'
    assert not m._stage(job, directory).exists()
    new = received(installation, raw, 'note.md')
    shutil.rmtree(m._stage(new, directory))  # Snapshot restores DB, not staging.
    m.process_next(directory)
    lost = m.get_job(new, owner, directory=directory)
    assert lost['state'] == 'failed' and not lost['retryable']
    assert 'restaurada' in lost['error']
    assert counts(directory) == (0, 0, 0, 0)


def test_worker_directory_is_captured_even_if_process_environment_changes(installation, tmp_path, monkeypatch):
    directory, owner = installation
    job = received(installation, b'# Captured instance\nUnique source', 'note.md')
    monkeypatch.setenv('MIA_DATA_DIR', str(tmp_path / 'different-installation'))
    m.process_next(directory)
    assert m.get_job(job, owner, directory=directory)['state'] == 'review'
    assert not (tmp_path / 'different-installation' / 'mia.db').exists()


def test_authorized_pending_jobs_reserve_owner_bytes_and_document_quota(installation, monkeypatch):
    directory, owner = installation
    raw = b'# Reserved source\n' + b'x' * 40
    first = received(installation, raw, 'first.md')
    drain(installation, first)
    second = received(installation, raw + b' second', 'second.md')
    drain(installation, second)
    monkeypatch.setattr(m, 'MAX_OWNER_TEXT', 100)
    m.confirm(first, m.Confirm(), owner, directory=directory)
    with pytest.raises(HTTPException) as error:
        m.confirm(second, m.Confirm(), owner, directory=directory)
    assert error.value.status_code == 409
    assert m.get_job(second, owner, directory=directory)['report']['selected'] == 0
    monkeypatch.setattr(m, 'MAX_OWNER_TEXT', 10_000)
    monkeypatch.setattr(m, 'MAX_OWNER_DOCUMENTS', 1)
    with pytest.raises(HTTPException) as error:
        m.confirm(second, m.Confirm(), owner, directory=directory)
    assert error.value.status_code == 409
    drain(installation, first, ('completed',))
    with m._connection(directory) as connection:
        assert tuple(connection.execute('SELECT document_bytes,document_count FROM migration_storage WHERE owner_id=1').fetchone()) == (len(raw), 1)
    m.remove(first, owner, directory=directory)
    with m._connection(directory) as connection:
        assert tuple(connection.execute('SELECT document_bytes,document_count FROM migration_storage WHERE owner_id=1').fetchone()) == (0, 0)


def test_large_monolithic_export_needs_no_manual_split_and_bad_tail_is_atomic(installation):
    directory, owner = installation
    conversations = [{'uuid': f'conversation-{i}', 'name': f'Synthetic conversation {i}',
                      'chat_messages': [{'uuid': f'message-{i}', 'sender': 'human', 'text': ('Large preserved source text. ' * 400) + str(i)}]} for i in range(800)]
    raw = json.dumps(conversations).encode()
    assert len(raw) > m.MAX_FILE
    job = received(installation, raw, 'claude.json')
    review = drain(installation, job)
    assert review['report']['recognized'] == 800
    assert counts(directory) == (0, 0, 0, 0)
    m.confirm(job, m.Confirm(), owner, directory=directory)
    done = drain(installation, job, ('completed',))
    assert done['report']['indexed'] == 800
    assert counts(directory)[0] == 800
    broken = received(installation, raw[:-1], 'truncated-export.json')
    m.process_next(directory)
    failed = m.get_job(broken, owner, directory=directory)
    assert failed['state'] == 'failed'
    assert failed['report']['recognized'] == 0 and failed['report']['entries']['errors'] == 1
    assert [path.name for path in m._stage(broken, directory).iterdir()] == ['upload']
    assert counts(directory)[0] == 800


def test_removal_cleanup_retries_after_database_commit(installation, monkeypatch):
    directory, owner = installation
    job = received(installation, b'# Private staging\nSynthetic source', 'note.md')
    cleanup = m._cleanup

    def unavailable(*_args):
        raise PermissionError('synthetic cleanup failure')

    monkeypatch.setattr(m, '_cleanup', unavailable)
    with pytest.raises(HTTPException) as error:
        m.remove(job, owner, directory=directory)
    assert error.value.status_code == 503
    assert m._stage(job, directory).exists()
    with m._connection(directory) as connection:
        assert not connection.execute('SELECT 1 FROM migration_jobs WHERE id=?', (job,)).fetchone()
        assert connection.execute('SELECT 1 FROM migration_cleanup WHERE job_id=?', (job,)).fetchone()
    monkeypatch.setattr(m, '_cleanup', cleanup)
    m.expire_staging(directory)
    assert not m._stage(job, directory).exists()
    with m._connection(directory) as connection:
        assert not connection.execute('SELECT 1 FROM migration_cleanup').fetchone()


@pytest.mark.parametrize('phase', ['receiving', 'review', 'indexing'])
def test_snapshot_restore_reconciles_all_nonterminal_jobs_without_staging(installation, phase):
    directory, owner = installation
    raw = b'# Restored source\nPrivate text awaiting review'
    if phase == 'receiving':
        job = m.create_upload(m.CreateUpload(filename='note.md', size=len(raw), sha256=hashlib.sha256(raw).hexdigest()), owner, directory)['id']
        m.append_upload(job, 0, raw[:8], owner, directory)
    else:
        job = received(installation, raw, 'note.md')
        drain(installation, job)
        if phase == 'indexing':
            m.confirm(job, m.Confirm(), owner, directory=directory)
    shutil.rmtree(m._stage(job, directory))
    m.initialize(directory)
    state = m.get_job(job, owner, directory=directory)
    assert state['state'] == 'failed' and not state['retryable']
    assert 'nova migração' in state['error'] and 'aprovadas foram preservadas' in state['error']
    with pytest.raises(HTTPException) as error:
        if phase == 'receiving':
            m.append_upload(job, 8, raw[8:], owner, directory)
        else:
            m.confirm(job, m.Confirm(), owner, directory=directory)
    assert error.value.status_code == 409
    assert counts(directory) == (0, 0, 0, 0)


@pytest.mark.parametrize('restart', [True, False])
def test_all_publication_checkpoints_survive_interrupted_finalization_and_lost_stage(installation, monkeypatch, restart):
    directory, owner = installation
    job = received(installation, archive([(f'work/{i}.md', f'Checkpointed source {i}') for i in range(20)]))
    drain(installation, job)
    m.confirm(job, m.Confirm(), owner, directory=directory)
    complete = m._complete_index

    def interruption(*_args):
        raise RuntimeError('synthetic process interruption before terminal commit')

    monkeypatch.setattr(m, '_complete_index', interruption)
    with pytest.raises(RuntimeError):
        m.process_next(directory)
    assert m.get_job(job, owner, directory=directory)['state'] == 'indexing'
    assert counts(directory)[0] == 20
    assert m._stage(job, directory).exists()  # Final transaction never deleted it.
    # Also tolerate the old problematic ordering / restored DB-only snapshot.
    shutil.rmtree(m._stage(job, directory))
    monkeypatch.setattr(m, '_complete_index', complete)
    if restart:
        m.initialize(directory)
    else:
        m.process_next(directory)
    result = m.get_job(job, owner, directory=directory)
    assert result['state'] == 'completed' and result['report']['indexed'] == 20
    assert counts(directory)[0] == 20


def test_interrupted_post_commit_cleanup_does_not_downgrade_completed_job(installation, monkeypatch):
    directory, owner = installation
    job = received(installation, b'# Persisted\nAlready checkpointed', 'note.md')
    drain(installation, job)
    m.confirm(job, m.Confirm(), owner, directory=directory)
    cleanup = m._cleanup

    def unavailable(*_args):
        raise PermissionError('synthetic interruption after terminal commit')

    monkeypatch.setattr(m, '_cleanup', unavailable)
    m.process_next(directory)
    result = m.get_job(job, owner, directory=directory)
    assert result['state'] == 'completed' and result['report']['indexed'] == 1
    assert result['raw_retained']
    monkeypatch.setattr(m, '_cleanup', cleanup)
    m.initialize(directory)
    assert not m.get_job(job, owner, directory=directory)['raw_retained']
