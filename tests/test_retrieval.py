"""Synthetic sources only: relevance, long-note boundaries and revocation."""
import hashlib
import uuid

from test_app import client, setup_payload
from mia import knowledge
from mia.db import connect, initialize, transaction
from mia.security import iso


def store(area, text, path='source.md', active=True):
    doc=str(uuid.uuid4())
    with transaction() as db:
        db.execute('INSERT INTO documents(id,owner_id,area_id,title,path,kind,content,hash,created_at,active) VALUES(?,1,?,?,?,\'markdown\',?,?,?,?)',
                   (doc,area,path,path,text,hashlib.sha256(text.encode()).hexdigest(),iso(),int(active)))
        for ordinal,chunk in enumerate(knowledge.chunk_content(text)):
            db.execute('INSERT INTO chunks VALUES(?,?,?,?)',(doc,ordinal,chunk,knowledge.normalized(chunk)))
    return doc


def test_long_note_late_evidence_and_document_diversity(client):
    browser,_=client
    browser.post('/api/setup',json=setup_payload())
    area=browser.get('/api/areas').json()[0]['id']
    text=('# Pesquisa\n\n'+('Registro de observação comum, sem conclusão atual.\n\n'*1200)
          +'# Decisão de lançamento\n\nDecidimos usar protocolo âmbar; revisão marcada para novembro.\n\n')
    late=store(area,text,'longa.md')
    second=store(area,'Outra evidência sobre protocolo âmbar: Ana revisará a proposta.','apoio.md')
    paused=store(area,'Protocolo âmbar protocolo âmbar prioridade falsa.','pausada.md',False)
    other=browser.post('/api/areas',json={'name':'Outra'}).json()['id']
    otherdoc=store(other,'Protocolo âmbar privado de outra área.','outra.md')
    sources=knowledge.retrieve({'id':1},area,'protocolo ambar',limit=3)
    assert {s['id'] for s in sources}=={late,second}
    assert all(s['id'] not in {paused,otherdoc} for s in sources)
    assert next(s for s in sources if s['id']==late)['ordinal']>20
    assert any('novembro' in s['content'] for s in sources)
    assert all(len(s['content'])<=1800 and s['hash'] for s in sources)
    assert otherdoc in {s['id'] for s in knowledge.retrieve({'id':1},None,'protocolo ambar',limit=6)}


def test_fts_index_migration_updates_and_deletion(client):
    browser,_=client
    browser.post('/api/setup',json=setup_payload())
    area=browser.get('/api/areas').json()[0]['id']
    doc=store(area,'Decisão antiga observatório','legacy.md')
    with connect() as db:
        for trigger in ('chunk_search_insert','chunk_search_update','chunk_search_delete'):
            db.execute('DROP TRIGGER '+trigger)
        db.execute('DROP TABLE chunk_search')
    initialize()
    assert knowledge.retrieve({'id':1},area,'observatorio')[0]['id']==doc
    with transaction() as db:
        db.execute('UPDATE chunks SET content=?,searchable=? WHERE document_id=?',('Novo protocolo celeste','novo protocolo celeste',doc))
    assert not knowledge.retrieve({'id':1},area,'observatorio')
    assert knowledge.retrieve({'id':1},area,'celeste')[0]['id']==doc
    with transaction() as db:
        db.execute('DELETE FROM documents WHERE id=?',(doc,))
    assert not knowledge.retrieve({'id':1},area,'celeste')
    with connect() as db:
        assert db.execute('SELECT count(*) FROM chunk_search').fetchone()[0]==0


def test_query_operators_are_plain_text_and_unapproved_cannot_displace(client):
    browser,_=client
    browser.post('/api/setup',json=setup_payload())
    area=browser.get('/api/areas').json()[0]['id']
    doc=store(area,'Pesquisa neblina com critérios explícitos','autorizada.md')
    for number in range(40):
        store(area,f'neblina neblina neblina {number}','pausada-'+str(number)+'.md',False)
    sources=knowledge.retrieve({'id':1},area,'"neblina" OR * NEAR(foo) -exclude',limit=1)
    assert [s['id'] for s in sources]==[doc]
    assert not knowledge.retrieve({'id':2},None,'neblina')
    assert not knowledge.retrieve({'id':1},area,'de do da com para')


def test_chunk_boundaries_preserve_phrases_without_mutating_original():
    text=('linha da nota.\n\n'*150)+'terminologia importante que cruza uma fronteira '+('sufixo '*500)
    chunks=knowledge.chunk_content(text)
    assert len(chunks)>2
    assert all(0<len(chunk)<=1800 for chunk in chunks)
    assert any('terminologia importante que cruza uma fronteira' in chunk for chunk in chunks)
    assert chunks[-1].endswith('sufixo ')
