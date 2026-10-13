import {fileChecksum, folderInventory, folderArchive} from './upload-files.js';

const stateNames={receiving:'Recebendo arquivo',inventory:'Conferindo o material',review:'Pronto para sua revisão',indexing:'Preparando fontes para usar',completed:'Grupos autorizados importados',partial:'Concluída com pendências',cancelled:'Importação cancelada',failed:'Importação interrompida'};
const megabytes=bytes=>(Number(bytes || 0)/1024/1024).toLocaleString('pt-BR',{maximumFractionDigits:1})+' MB';

export async function migrationPanel(panel, ctx) {
  const {api,esc,errorMessage,refresh,navigate,bindDocuments}=ctx;
  let transfer=null,current=null,page=0,query='',selection=new Set(),excluded=new Set(),selectionQueue=Promise.resolve(),selectionLoaded=false;
  const batches=await api('/api/migrations');
  if(!panel.isConnected)return;
  panel.innerHTML='<div class="section-head"><div><p class="kicker">TRAZER CONTEXTO</p><h2>Seu trabalho já tem uma história.</h2></div></div>'+ 
    '<p class="lede">Traga notas, pastas e conversas para começar de onde você parou. Primeiro você confere o material; só depois autoriza a Biblioteca.</p>'+ 
    '<p class="notice">Arquivos enviados são copiados para esta instalação da Mia. Um ZIP inteiro pode conter mídia e configurações que serão ignoradas depois de recebido. Importar não envia conteúdo à IA, não altera seus originais e não executa plugins.</p>'+ 
    '<form class="form" id="migration-form"><label>De onde vem este material?<select name="source_kind"><option value="obsidian">Obsidian ou pasta de notas</option><option value="files">Arquivos Markdown e texto</option><option value="chatgpt">Exportação do ChatGPT</option><option value="claude">Exportação do Claude</option><option value="drive">Arquivos baixados do Drive ou outro serviço</option></select></label>'+ 
    '<p id="migration-format" class="subtle">Escolha um ZIP do vault ou arquivos Markdown. Configurações, plugins e mídia não entram no índice de texto.</p>'+ 
    '<label>Escolher arquivos<input name="file" type="file" accept=".zip,.md,.markdown,.txt,.json" multiple required></label>'+ 
    '<div class="actions"><button type="submit" class="btn primary">Conferir material</button><button type="button" class="btn" id="choose-folder">Escolher uma pasta</button><input type="file" id="migration-folder" webkitdirectory multiple hidden aria-label="Escolher uma pasta"></div>'+ 
    '<p class="subtle">Transferências abandonadas expiram após sete dias. No celular, use arquivos ou um ZIP se o seletor de pastas não estiver disponível. Drive: apenas arquivos baixados/exportados; não há conexão com sua conta. Arquivos .gdoc são atalhos e não contêm o texto do documento.</p></form>'+ 
    '<div id="migration-transfer" class="section" aria-live="polite"></div><section id="migration-detail" class="section"></section>'+ 
    '<section class="section"><h3>Minhas importações</h3><div class="list" id="migration-batches"></div></section>';
  const form=panel.querySelector('#migration-form'),progress=panel.querySelector('#migration-transfer'),detail=panel.querySelector('#migration-detail');
  const descriptions={obsidian:'Escolha um ZIP do vault, uma pasta ou arquivos Markdown. Configurações, plugins e mídia não entram no índice de texto.',files:'Markdown, texto e lotes ZIP. Escolha vários arquivos de uma vez; a revisão será agrupada por pasta.',chatgpt:'Exportações JSON/ZIP reconhecidas do ChatGPT. A revisão informa conversas, papéis e limitações; anexos e ramificações não lidos ficam no relatório.',claude:'Exportações JSON/ZIP reconhecidas do Claude. Mensagens do usuário e da IA mantêm seus papéis; uma fala do assistente não vira um fato sobre você.',drive:'Baixe/exporte os arquivos no serviço e selecione-os aqui. Textos/Markdown/exports reconhecidos entram na Biblioteca; PDF, formatos de escritório e atalhos .gdoc ainda não são lidos.'};
  form.elements.source_kind.onchange=()=>{panel.querySelector('#migration-format').textContent=descriptions[form.elements.source_kind.value];};
  function showProgress(message,received=0,total=0){
    progress.innerHTML='<p role="status">'+esc(message)+'</p>'+(total?'<progress max="'+total+'" value="'+received+'" aria-label="Progresso da transferência"></progress><p class="subtle">'+megabytes(received)+' de '+megabytes(total)+'</p>':'')+(transfer?'<button type="button" class="btn" id="pause-upload">Pausar transferência</button>':'');
    progress.querySelector('#pause-upload')?.addEventListener('click',()=>transfer?.abort());
  }
  function listBatches(rows){
    panel.querySelector('#migration-batches').innerHTML=rows.length?rows.map(batch=>'<article class="migration-row"><div><h3>'+esc(batch.filename)+'</h3><p class="subtle">'+esc(stateNames[batch.state] || batch.state)+' · '+megabytes(batch.size)+'</p></div><button class="btn" data-open-migration="'+esc(batch.id)+'">'+(batch.state==='review'?'Revisar':'Ver importação')+'</button></article>').join(''):'<p class="subtle">Nenhuma importação ainda. Sua Mia começa sem contexto pessoal.</p>';
    panel.querySelectorAll('[data-open-migration]').forEach(button=>button.onclick=()=>openBatch(button.dataset.openMigration).catch(errorMessage));
  }
  listBatches(Array.isArray(batches)?batches:batches.migrations || []);
  async function reloadList(){if(panel.isConnected)listBatches(await api('/api/migrations'));}
  async function sendFiles(files,isFolder=false){
    if(transfer)throw new Error('Aguarde ou pause a transferência atual');
    if(!files.length)return;
    transfer=new AbortController();const signal=transfer.signal;
    const button=form.querySelector('[type=submit]');button.disabled=true;
    try {
      let file=files[0],clientNotSent=0;
      if(isFolder || files.length>1){
        const inventory=folderInventory(files);clientNotSent=inventory.ignored.length;
        if(!inventory.accepted.length)throw new Error('Esta seleção não contém Markdown, texto ou JSON reconhecível');
        if(inventory.size>100*1024*1024)throw new Error('Os arquivos de texto selecionados excedem 100 MB. Nenhum arquivo foi enviado.');
        if(!window.confirm('Enviar '+inventory.accepted.length+' arquivos de texto ('+megabytes(inventory.size)+')? '+inventory.ignored.length+' arquivos de mídia, formatos não suportados ou configurações ficam neste dispositivo e não serão enviados.'))return;
        showProgress('Preparando a pasta; os arquivos originais permanecem intactos.');
        file=await folderArchive(inventory,(n,total)=>showProgress('Preparando '+n+' de '+total+' arquivos.'),signal);
      }
      if(file.size>100*1024*1024)throw new Error('O arquivo excede o limite de 100 MB. Nenhum arquivo foi enviado.');
      showProgress('Conferindo integridade antes de transferir…',0,file.size);
      const checksum=await fileChecksum(file,(n,total)=>showProgress('Conferindo integridade antes de transferir…',n,total),signal);
      const existing=await api('/api/migrations');
      let batch=existing.find(b=>b.state==='receiving' && b.sha256===checksum && b.size===file.size && b.filename===file.name);
      if(batch)batch=await api('/api/migrations/'+batch.id);
      else batch=await api('/api/migrations',{method:'POST',body:JSON.stringify({filename:file.name,size:file.size,sha256:checksum,source_kind:form.elements.source_kind.value,client_not_sent:clientNotSent})});
      current=batch.id;let offset=batch.received || 0;
      const chunkSize=Math.min(1024*1024,batch.limits?.chunk_bytes || 1024*1024);
      while(offset<file.size){
        if(signal.aborted)throw new DOMException('Transferência pausada','AbortError');
        showProgress('Transferindo '+file.name+'. O progresso fica salvo para retomar.',offset,file.size);
        try{batch=await api('/api/migrations/'+batch.id+'/upload?offset='+offset,{method:'PATCH',headers:{'Content-Type':'application/octet-stream'},body:file.slice(offset,offset+chunkSize),signal});}
        catch(error){if(error.status!==409)throw error;const latest=await api('/api/migrations/'+batch.id);if(latest.sha256!==checksum || latest.received<=offset || latest.received>file.size)throw error;batch=latest;}
        if(!Number.isInteger(batch.received) || batch.received<=offset)throw new Error('A transferência não avançou; confira a importação antes de retomar');
        offset=batch.received;
      }
      await api('/api/migrations/'+batch.id+'/finish',{method:'POST',body:'{}'});
      showProgress('Arquivo recebido. A Mia está conferindo o material para sua revisão.',file.size,file.size);
      await reloadList();await openBatch(batch.id);
    } catch(error){
      showProgress(error.name==='AbortError'?'Transferência pausada. Escolha o mesmo arquivo ou pasta para continuar do ponto recebido.':error.message);
      if(error.name!=='AbortError')throw error;
    } finally {transfer=null;button.disabled=false;progress.querySelector('#pause-upload')?.remove();}
  }
  form.onsubmit=event=>{event.preventDefault();sendFiles([...form.elements.file.files]).catch(errorMessage);};
  const folder=panel.querySelector('#migration-folder'),folderButton=panel.querySelector('#choose-folder');
  if(!('webkitdirectory' in folder)){folderButton.disabled=true;folderButton.textContent='Use um ZIP desta pasta';}
  folderButton.onclick=()=>folder.click();folder.onchange=()=>sendFiles([...folder.files],true).catch(errorMessage);

  async function openBatch(id,keepSelection=false){
    if(current!==id){page=0;query='';selectionLoaded=false;}
    current=id;
    const batch=await api('/api/migrations/'+id+'?offset='+page*50+'&limit=50&q='+encodeURIComponent(query));
    if(!panel.isConnected || current!==id)return;
    if(!keepSelection || !selectionLoaded){const chosen=batch.selected_groups || ['*'];selection=new Set(chosen.includes('*')?(batch.groups || []).map(group=>group.id):chosen);excluded=new Set(batch.excluded_ids || []);selectionLoaded=batch.state==='review';}
    const groups=batch.groups || [],report=batch.report || {},items=batch.items || [];
    detail.innerHTML='<div class="section-head"><h3>'+esc(batch.filename)+'</h3><span class="badge">'+esc(stateNames[batch.state] || batch.state)+'</span></div>'+ 
      (batch.error?'<p class="notice">'+esc(batch.error)+'</p>':'')+
      (batch.state==='receiving'?'<p class="notice">'+megabytes(batch.received)+' de '+megabytes(batch.size)+' recebidos. Para retomar, escolha o mesmo arquivo acima. Ainda não há fontes novas na Biblioteca.</p>':'')+
      (['inventory','indexing'].includes(batch.state)?'<p role="status">'+(batch.state==='inventory'?'Conferindo arquivos, formatos e conversas. Pode voltar depois; esta etapa continua na instalação.':'Preparando apenas os grupos autorizados. As fontes prontas já podem ser usadas; a cobertura ainda é parcial.')+'</p>':'')+
      (batch.state==='completed' && !batch.coverage_complete?'<p class="notice">Os grupos autorizados já podem ser usados. A cobertura tem exclusões, formatos ignorados ou limitações; confira o relatório antes de considerar a migração completa.</p>':'')+
      '<details '+(['partial','failed','cancelled'].includes(batch.state)?'open':'')+'><summary>Cobertura, ignorados e limitações</summary><pre class="source-preview">'+esc(JSON.stringify(report,null,2))+'</pre></details>'+ 
      (batch.state==='review'?'<p class="lede">Escolha pastas ou grupos inteiros. Você pode abrir prévias e desmarcar exceções sem selecionar nota por nota.</p><form id="migration-selection"><div class="actions"><button type="button" class="btn" id="migration-select-all">Todos os grupos</button><button type="button" class="btn" id="migration-select-none">Nenhum grupo</button></div><div class="group-grid">'+groups.map(group=>'<label class="group-option"><input type="checkbox" name="group" value="'+esc(group.id)+'" '+(selection.has(group.id)?'checked':'')+'><span>'+esc(group.name || group.id)+'<small>'+Number(group.total || 0)+' documentos/conversas</small></span></label>').join('')+'</div><label>Encontrar uma prévia<input type="search" id="migration-query" value="'+esc(query)+'" placeholder="Título ou caminho"></label><div class="list" id="migration-items">'+items.map(item=>'<article class="candidate"><label class="check-label"><input name="item" type="checkbox" value="'+esc(item.id)+'" '+(!excluded.has(item.id)&&selection.has(item.group)?'checked':'')+' '+(!selection.has(item.group)?'disabled':'')+'>'+esc(item.title)+'</label><p class="subtle">'+esc(item.path)+' · '+esc(item.kind)+' · '+Number(item.characters || 0)+' caracteres</p><details><summary>Prévia</summary><pre class="source-preview">'+esc(item.preview || '')+'</pre></details></article>').join('')+'</div><div class="actions"><button type="button" class="btn" id="migration-prev" '+(page===0?'disabled':'')+'>Anteriores</button><span class="subtle">'+(page*50+1)+'–'+(page*50+items.length)+' de '+Number(batch.total || 0)+'</span><button type="button" class="btn" id="migration-next" '+((page+1)*50>=(batch.total || 0)?'disabled':'')+'>Próximas</button></div><p class="subtle" id="selection-state" role="status">A seleção é salva nesta instalação antes de importar. Estas fontes ainda não entram na busca nem na IA.</p><button class="btn primary" type="submit" id="confirm-migration">Autorizar e importar grupos</button></form>':'')+
      (['completed','partial','cancelled'].includes(batch.state)?'<div class="actions"><button class="btn" id="migration-use">Usar fontes já disponíveis</button></div>':'')+
      (!['completed','cancelled'].includes(batch.state)?'<button class="btn ghost" id="cancel-migration">Cancelar importação</button>':'')+
      (['completed','partial','cancelled'].includes(batch.state)?'<button class="btn ghost" id="delete-migration">Excluir lote e fontes exclusivas</button>':'')+
      (batch.state==='failed'?'<button class="btn" id="retry-migration">Tentar etapa novamente</button>':'');
    async function persist(){
      const values={groups:[...selection],excluded_ids:[...excluded]};
      selectionQueue=selectionQueue.catch(()=>{}).then(()=>api('/api/migrations/'+id+'/selection',{method:'PUT',body:JSON.stringify(values)}));
      await selectionQueue;if(detail.isConnected)detail.querySelector('#selection-state')?.replaceChildren(document.createTextNode('Seleção salva. Só entra na Biblioteca após sua autorização.'));
    }
    const selectionForm=detail.querySelector('#migration-selection');
    if(selectionForm){
      async function updateGroups(){selection=new Set([...selectionForm.querySelectorAll('[name=group]:checked')].map(input=>input.value));await persist();await openBatch(id,true);}
      selectionForm.querySelectorAll('[name=group]').forEach(input=>input.onchange=()=>updateGroups().catch(errorMessage));
      selectionForm.querySelectorAll('[name=item]').forEach(input=>input.onchange=()=>{if(input.checked)excluded.delete(input.value);else excluded.add(input.value);persist().catch(errorMessage);});
      selectionForm.querySelector('#migration-select-all').onclick=()=>{selectionForm.querySelectorAll('[name=group]').forEach(input=>input.checked=true);updateGroups().catch(errorMessage);};
      selectionForm.querySelector('#migration-select-none').onclick=()=>{selectionForm.querySelectorAll('[name=group]').forEach(input=>input.checked=false);updateGroups().catch(errorMessage);};
      let searchTimer;selectionForm.querySelector('#migration-query').oninput=event=>{clearTimeout(searchTimer);query=event.target.value;page=0;searchTimer=setTimeout(()=>openBatch(id,true).catch(errorMessage),350);};
      selectionForm.querySelector('#migration-prev').onclick=()=>{page=Math.max(0,page-1);openBatch(id,true).catch(errorMessage);};
      selectionForm.querySelector('#migration-next').onclick=()=>{page++;openBatch(id,true).catch(errorMessage);};
      selectionForm.onsubmit=async event=>{
        event.preventDefault();const button=selectionForm.querySelector('[type=submit]');button.disabled=true;
        try{if(!selection.size)throw new Error('Escolha pelo menos um grupo');await selectionQueue;await api('/api/migrations/'+id+'/confirm',{method:'POST',body:JSON.stringify({groups:[...selection],excluded_ids:[...excluded]})});await reloadList();await openBatch(id);}
        catch(error){errorMessage(error);if(button.isConnected)button.disabled=false;}
      };
    }
    detail.querySelector('#cancel-migration')?.addEventListener('click',async()=>{
      if(!window.confirm('Cancelar este lote? As fontes que já entraram continuam disponíveis; o relatório informa a cobertura. Os originais não serão alterados.'))return;
      try{if(transfer)transfer.abort();await api('/api/migrations/'+id+'/cancel',{method:'POST',body:'{}'});await reloadList();await openBatch(id);}catch(error){errorMessage(error);}
    });
    detail.querySelector('#delete-migration')?.addEventListener('click',async()=>{if(!window.confirm('Excluir este lote e as fontes que só pertencem a ele? Fontes compartilhadas com outras importações e registros de conversas anteriores serão preservados.'))return;try{await api('/api/migrations/'+id,{method:'DELETE'});await refresh();navigate('library');}catch(error){errorMessage(error);}});
    detail.querySelector('#retry-migration')?.addEventListener('click',async()=>{try{await api('/api/migrations/'+id+'/resume',{method:'POST',body:'{}'});await openBatch(id);}catch(error){errorMessage(error);}});
    detail.querySelector('#migration-use')?.addEventListener('click',async()=>{await refresh();navigate('today');});
    bindDocuments();
    if(['inventory','indexing'].includes(batch.state))setTimeout(()=>{if(panel.isConnected && current===id)openBatch(id,true).then(reloadList).catch(errorMessage);},1400);
  }
  const active=(Array.isArray(batches)?batches:[]).find(batch=>['receiving','inventory','review','indexing','failed'].includes(batch.state));
  if(active)await openBatch(active.id);
}
