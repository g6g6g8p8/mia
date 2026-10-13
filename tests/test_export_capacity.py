"""Large private exports preserve content without collecting the library in RAM."""
import hashlib
import io
import json
import tracemalloc
import zipfile

from mia.db import transaction
from mia.security import iso
from test_app import client, setup_payload


def test_large_library_export_is_bounded_and_complete(client):
    browser, _ = client
    browser.post('/api/setup', json=setup_payload())
    area = browser.get('/api/areas').json()[0]['id']
    # More than 20 MiB of approved content; ZIP compression intentionally keeps
    # the test client's response collection out of the memory measurement.
    with transaction() as db:
        for index in range(100):
            text = 'Fonte sintética ' + str(index) + '\n' + ('Texto privado de validação.\n' * 8500)
            db.execute('INSERT INTO documents(id,owner_id,area_id,title,path,kind,content,hash,created_at) VALUES(?,1,?,?,?,?,?,?,?)',
                       (str(index),area,'Fonte '+str(index),str(index)+'.md','markdown',text,hashlib.sha256(text.encode()).hexdigest(),iso()))
    tracemalloc.start()
    try:
        exported = browser.get('/api/export')
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert exported.status_code == 200
    assert exported.headers['cache-control'] == 'no-store'
    assert peak < 16 * 1024 * 1024, 'Export collected the whole library in memory'
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        payload = json.loads(archive.read('mia-export.json'))
    assert len(payload['documents']) == 100
    for document in payload['documents']:
        assert hashlib.sha256(document['content'].encode()).hexdigest() == document['hash']
    # Response cleanup must release the export guard after successful delivery.
    assert browser.get('/api/export').status_code == 200


def test_export_failure_releases_guard_and_preserves_data(client, monkeypatch):
    from mia import app
    import shutil
    browser, _ = client
    browser.post('/api/setup', json=setup_payload())
    with monkeypatch.context() as patch:
        patch.setattr(shutil,'disk_usage',lambda _path: type('Capacity',(),{'free':0})())
        assert browser.get('/api/export').status_code == 507
    assert browser.get('/api/export').status_code == 200
    assert not app.EXPORT_LOCK.locked()
