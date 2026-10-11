"""Local, reviewed imports. No archive extraction, remote fetch, model call or execution."""
import base64
import binascii
import hashlib
import io
import json
import re
import stat
import unicodedata
import uuid
import zipfile
from pathlib import PurePosixPath

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .db import connect, transaction
from .security import iso

MAX_UPLOAD = 8 * 1024 * 1024
MAX_EXPANDED = 20 * 1024 * 1024
MAX_TEXT = 200_000


class ImportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    area_id: str = Field(min_length=1,max_length=80)
    filename: str = Field(min_length=1,max_length=200)
    content_base64: str = Field(max_length=11_200_000)


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_ids: list[str] = Field(min_length=1,max_length=500)


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c))


def safe_path(name):
    if '\\' in name or '\x00' in name or re.match(r'^[A-Za-z]:',name):
        raise ValueError('Caminho não permitido')
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or len(path.parts)>12:
        raise ValueError('Caminho não permitido')
    return str(path)


def conversations(data):
    if not isinstance(data,list) or len(data)>500:
        raise ValueError('Esperada lista de até 500 conversas')
    output=[]
    for conversation in data:
        if not isinstance(conversation,dict): raise ValueError('Conversa inválida')
        messages=[]
        if isinstance(conversation.get('mapping'),dict):
            mapping=conversation['mapping']
            node=conversation.get('current_node')
            if not node or len(mapping)>10000: raise ValueError('Ramo atual ausente ou conversa muito grande')
            seen=set(); chain=[]
            while node:
                if node in seen or node not in mapping: raise ValueError('Árvore de conversa inválida')
                seen.add(node); item=mapping[node]; chain.append(item.get('message')); node=item.get('parent')
            for m in reversed(chain):
                if not m: continue
                role=m.get('author',{}).get('role','unknown')
                if role not in ('user','assistant'): continue
                parts=m.get('content',{}).get('parts',[])
                text='\n'.join(p for p in parts if isinstance(p,str))
                if text: messages.append({'role':role,'time':m.get('create_time'),'text':text})
            kind='chatgpt'
        elif isinstance(conversation.get('chat_messages'),list):
            if len(conversation['chat_messages'])>10000: raise ValueError('Conversa muito grande')
            for m in conversation['chat_messages']:
                role={'human':'user','assistant':'assistant'}.get(m.get('sender'),'unknown')
                if role=='unknown': continue
                text=m.get('text')
                if not isinstance(text,str):
                    text='\n'.join(p.get('text','') for p in m.get('content',[]) if isinstance(p,dict) and p.get('type')=='text')
                if text: messages.append({'role':role,'time':m.get('created_at'),'text':text})
            kind='claude'
        else:
            raise ValueError('Formato JSON não reconhecido; use Markdown ou texto')
        title=str(conversation.get('title') or conversation.get('name') or 'Conversa sem título')[:200]
        content='\n\n'.join(f"[{m['role']} · {m['time'] or 'data não informada'}]\n{m['text']}" for m in messages)
        if not content.strip(): raise ValueError('Conversa sem mensagens textuais legíveis')
        if len(content)>MAX_TEXT: raise ValueError('Conversa excede 200.000 caracteres; divida o arquivo')
        output.append((title,kind,content))
    return output


def decode_entry(path,raw):
    text=raw.decode('utf-8-sig')
    if '\x00' in text: raise ValueError('Arquivo binário não suportado')
    suffix=PurePosixPath(path).suffix.lower()
    if suffix=='.json':
        return conversations(json.loads(text))
    if len(text)>MAX_TEXT: raise ValueError('Nota excede 200.000 caracteres')
    if not text.strip(): raise ValueError('Arquivo vazio')
    title=next((line.lstrip('# ').strip()[:200] for line in text.splitlines() if line.startswith('# ')),PurePosixPath(path).stem[:200])
    return [(title,'markdown' if suffix=='.md' else 'text',text)]


def prepare(payload,owner):
    with connect() as db:
        if not db.execute('SELECT 1 FROM areas WHERE id=? AND owner_id=?',(payload.area_id,owner['id'])).fetchone():
            raise HTTPException(404,'Área não encontrada')
        if db.execute("SELECT count(*) FROM imports WHERE owner_id=? AND state='review'",(owner['id'],)).fetchone()[0]>=3:
            raise HTTPException(409,'Revise ou cancele as importações pendentes primeiro')
    try:
        raw=base64.b64decode(payload.content_base64,validate=True)
        if len(raw)>MAX_UPLOAD: raise ValueError('Arquivo excede 8 MB')
        entries=[]
        if payload.filename.lower().endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                infos=archive.infolist()
                if len(infos)>300: raise ValueError('ZIP excede 300 entradas')
                if sum(i.file_size for i in infos)>MAX_EXPANDED: raise ValueError('ZIP expandido excede 20 MB')
                for info in infos:
                    path=safe_path(info.filename)
                    if stat.S_ISLNK(info.external_attr>>16) or info.flag_bits & 1:
                        raise ValueError('ZIP com link simbólico ou criptografia não suportado')
                    if info.is_dir(): continue
                    if info.file_size>8*1024*1024 or info.file_size>max(info.compress_size,1)*200:
                        raise ValueError('Expansão de arquivo excede limite')
                    if PurePosixPath(path).suffix.lower() not in ('.md','.txt','.json') or any(p.startswith('.') or p=='__MACOSX' for p in PurePosixPath(path).parts):
                        entries.append((path,None))
                    else:
                        entries.append((path,archive.read(info)))
        else:
            path=safe_path(payload.filename)
            if PurePosixPath(path).suffix.lower() not in ('.md','.txt','.json'): raise ValueError('Use Markdown, texto, JSON de conversas ou ZIP')
            entries=[(path,raw)]
        candidates=[]; report={'ignored':[],'errors':[],'notes':['Conversas: somente texto do ramo reconhecido; anexos, ferramentas e mídia não importados.']}
        for path,content in entries:
            if content is None:
                report['ignored'].append(path); continue
            try:
                for index,(title,kind,text) in enumerate(decode_entry(path,content)):
                    candidate_path=path if kind in ('markdown','text') else path+'#'+str(index+1)
                    candidates.append({'id':str(uuid.uuid4()),'path':candidate_path,'title':title,'kind':kind,'content':text,'hash':hashlib.sha256(text.encode()).hexdigest()})
                    if len(candidates)>500: raise ValueError('Lote excede 500 documentos')
            except (ValueError,TypeError,KeyError,AttributeError) as error:
                # Discard this entire entry on a parse error; no silent partial conversation.
                candidates=[c for c in candidates if c['path']!=path and not c['path'].startswith(path+'#')]
                report['errors'].append({'path':path,'reason':str(error)[:200]})
        if len(candidates)>500: raise ValueError('Lote excede 500 documentos')
        if not candidates: raise ValueError('Nenhum documento legível. Use notas Markdown/texto ou uma exportação JSON reconhecida.')
    except (ValueError,binascii.Error,zipfile.BadZipFile,RuntimeError,NotImplementedError,RecursionError) as error:
        raise HTTPException(422,str(error)[:200]) from error
    batch,created=str(uuid.uuid4()),iso()
    with transaction(immediate=True) as db:
        if db.execute("SELECT count(*) FROM imports WHERE owner_id=? AND state='review'",(owner['id'],)).fetchone()[0]>=3:
            raise HTTPException(409,'Revise ou cancele as importações pendentes primeiro')
        db.execute('INSERT INTO imports VALUES(?,?,?,?,?,?,?)',(batch,owner['id'],payload.area_id,payload.filename,'review',json.dumps(report),created))
        for c in candidates:
            db.execute('INSERT INTO import_items VALUES(?,?,?,?,?,?,?)',(c['id'],batch,c['path'],c['title'],c['kind'],c['content'],c['hash']))
    return get_batch(batch,owner)


def get_batch(batch,owner):
    with connect() as db:
        row=db.execute('SELECT * FROM imports WHERE id=? AND owner_id=?',(batch,owner['id'])).fetchone()
        if not row: raise HTTPException(404,'Importação não encontrada')
        result=dict(row); result.pop('owner_id'); result['report']=json.loads(result.pop('report_json'))
        result['items']=[dict(i) for i in db.execute('SELECT id,path,title,kind,substr(content,1,600) AS preview,length(content) AS characters FROM import_items WHERE import_id=?',(batch,))]
    return result


def commit(batch,selection,owner,audit):
    with transaction(immediate=True) as db:
        row=db.execute('SELECT * FROM imports WHERE id=? AND owner_id=?',(batch,owner['id'])).fetchone()
        if not row: raise HTTPException(404,'Importação não encontrada')
        if row['state']=='completed': return get_batch(batch,owner)
        if row['state']!='review': raise HTTPException(409,'Importação não aguarda revisão')
        selected=set(selection.item_ids)
        items=list(db.execute('SELECT * FROM import_items WHERE import_id=?',(batch,)))
        if not selected <= {item['id'] for item in items}: raise HTTPException(422,'Seleção não pertence a esta importação')
        imported=duplicates=0
        for item in items:
            if item['id'] not in selected: continue
            existing=db.execute('SELECT id FROM documents WHERE owner_id=? AND area_id=? AND hash=?',(owner['id'],row['area_id'],item['hash'])).fetchone()
            if existing:
                doc=existing['id']; duplicates+=1
            else:
                doc=str(uuid.uuid4()); imported+=1
                db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?)',(doc,owner['id'],row['area_id'],item['title'],item['path'],item['kind'],item['content'],item['hash'],iso()))
                for n,start in enumerate(range(0,len(item['content']),1000)):
                    chunk=item['content'][start:start+1200]
                    db.execute('INSERT INTO chunks VALUES(?,?,?,?)',(doc,n,chunk,normalized(chunk)))
            db.execute('INSERT OR IGNORE INTO document_imports VALUES(?,?,?)',(doc,batch,item['path']))
        report=json.loads(row['report_json']); report.update(imported=imported,duplicates=duplicates,not_selected=len(items)-len(selected))
        db.execute("UPDATE imports SET state='completed',report_json=? WHERE id=?",(json.dumps(report),batch))
        db.execute('DELETE FROM import_items WHERE import_id=?',(batch,))
        audit(db,owner['id'],'import.confirmed','import',batch,{'imported':imported,'duplicates':duplicates})
    return get_batch(batch,owner)


def remove(batch,owner,audit):
    with transaction(immediate=True) as db:
        row=db.execute('SELECT 1 FROM imports WHERE id=? AND owner_id=?',(batch,owner['id'])).fetchone()
        if not row: raise HTTPException(404,'Importação não encontrada')
        doc_ids=[r[0] for r in db.execute('SELECT DISTINCT document_id FROM document_imports WHERE import_id=?',(batch,))]
        db.execute('DELETE FROM imports WHERE id=?',(batch,))
        for doc in doc_ids:
            if not db.execute('SELECT 1 FROM document_imports WHERE document_id=?',(doc,)).fetchone():
                db.execute('DELETE FROM documents WHERE id=? AND owner_id=?',(doc,owner['id']))
        audit(db,owner['id'],'import.removed','import',batch)
    return {'ok':True}


def retrieve(owner,area_id,query,limit=3):
    terms=list(dict.fromkeys(re.findall(r'\w{2,}',normalized(query))))[:8]
    if not terms: return []
    terms=[t for t in terms if t not in {'que','para','uma','como','qual','quais','the','and','com','essa','area','esta'}] or terms
    conditions=['c.searchable LIKE ?' for _ in terms]
    values=['%'+t+'%' for t in terms]
    scope='d.owner_id=?'; scope_values=[owner['id']]
    if area_id: scope+=' AND d.area_id=?'; scope_values.append(area_id)
    sql=f"SELECT d.id,d.title,d.path,d.kind,d.area_id,d.created_at,c.ordinal,c.content FROM chunks c JOIN documents d ON d.id=c.document_id WHERE {scope} AND ({' OR '.join(conditions)}) ORDER BY ({' + '.join(conditions)}) DESC,d.id,c.ordinal LIMIT ?"
    with connect() as db:
        return [{'source':'doc:'+r['id'],**dict(r)} for r in db.execute(sql,scope_values+values+values+[limit])]


def document(doc,owner):
    with connect() as db:
        row=db.execute('SELECT * FROM documents WHERE id=? AND owner_id=?',(doc,owner['id'])).fetchone()
        if not row: raise HTTPException(404,'Fonte não encontrada')
        result=dict(row); result.pop('owner_id')
        result['origins']=[dict(r) for r in db.execute('SELECT import_id,path FROM document_imports WHERE document_id=?',(doc,))]
    return result
