export function locationCard(location, esc, compact=false) {
  const labels={local:'Neste computador',remote:'No seu servidor',unknown:'Confirme onde sua Mia está instalada'};
  const message=location?.description || 'Os arquivos ficam na instalação que está atendendo este endereço.';
  return '<section class="'+(compact?'location-note':'card location-card')+'"><p class="kicker">ONDE SEU CONTEXTO FICA</p><h3>'+esc(labels[location?.mode] || labels.unknown)+'</h3><p class="subtle">'+esc(message)+'</p>'+(compact?'':'<p class="subtle">Código no GitHub não é uma conta e não recebe automaticamente seus dados. Mac e iPhone acessando este mesmo endereço usam a mesma Biblioteca; não há sincronização offline entre instalações.</p>')+'</section>';
}

export async function focusPanel(panel, ctx, experience) {
  const {api,esc,errorMessage,refresh}=ctx;
  const [data,allDocs]=await Promise.all([experience || api('/api/experience'),api('/api/documents')]);
  if(!panel.isConnected)return;
  const docs=allDocs.filter(doc=>doc.active),focus=data.focus || {title:'',source_ids:[],revision:0};
  const selected=new Set(focus.source_ids || []);
  let page=0,query='';
  panel.innerHTML='<h2>O que vamos retomar?</h2><p class="lede">Escolha um foco atual e, se quiser, fontes que sustentam esse trabalho. Uma nota antiga não vira prioridade nem tarefa automaticamente.</p>'+
    '<form class="form" id="focus-form"><label>Meu foco agora<input name="title" id="focus-title" maxlength="200" placeholder="Ex.: retomar o projeto que ficou parado" value="'+esc(focus.title || '')+'"></label>'+
    (docs.length?'<fieldset><legend>Fontes para retomar</legend><p class="subtle">Encontre qualquer fonte ativa por título ou pasta. Escolha até 20; a seleção é mantida ao mudar de página.</p><label>Encontrar uma fonte<input type="search" id="focus-source-query" placeholder="Título ou caminho"></label><p id="focus-selection-count" class="subtle" role="status"></p><div id="focus-selected" class="actions"></div><div class="list" id="focus-sources"></div><div class="actions" id="focus-source-pages"></div></fieldset>':'<p class="notice">Você pode escolher um foco sem importar. Traga fontes quando quiser para retomá-lo com evidência.</p>')+
    (focus.unavailable_sources?'<p class="notice">'+Number(focus.unavailable_sources)+' fontes do foco anterior estão pausadas ou indisponíveis e não serão usadas.</p>':'')+
    '<button class="btn primary" type="submit" id="save-focus">Confirmar meu foco</button><p id="focus-saved" role="status"></p></form>';
  function selectedSources(){
    panel.querySelector('#focus-selection-count').textContent=selected.size+' de 20 fontes selecionadas';
    panel.querySelector('#focus-selected').innerHTML=[...selected].map(id=>'<button type="button" class="btn" data-unselect-focus="'+esc(id)+'" aria-label="Remover fonte do foco: '+esc(docs.find(doc=>doc.id===id)?.title || 'fonte')+'">'+esc(docs.find(doc=>doc.id===id)?.title || 'Fonte selecionada')+' ×</button>').join('');
    panel.querySelectorAll('[data-unselect-focus]').forEach(button=>button.onclick=()=>{selected.delete(button.dataset.unselectFocus);renderSources();});
  }
  function renderSources(){
    if(!panel.isConnected)return;
    const filtered=docs.filter(doc=>(doc.title+' '+doc.path).toLocaleLowerCase().includes(query.toLocaleLowerCase())),start=page*20;
    panel.querySelector('#focus-sources').innerHTML=filtered.slice(start,start+20).map(doc=>'<label class="check-label"><input name="source_ids" type="checkbox" value="'+esc(doc.id)+'" '+(selected.has(doc.id)?'checked':'')+'><span>'+esc(doc.title)+'<small>'+esc(doc.path || '')+'</small></span><button type="button" class="btn ghost source-peek" data-document="'+esc(doc.id)+'">Abrir fonte</button></label>').join('') || '<p class="subtle">Nenhuma fonte neste filtro. Tente outro título ou pasta.</p>';
    panel.querySelector('#focus-source-pages').innerHTML='<button class="btn" type="button" id="focus-sources-prev" '+(page===0?'disabled':'')+'>Anteriores</button><span class="subtle">'+filtered.length+' fontes · página '+(page+1)+'</span><button class="btn" type="button" id="focus-sources-next" '+(start+20>=filtered.length?'disabled':'')+'>Próximas</button>';
    panel.querySelector('#focus-sources-prev').onclick=()=>{page--;renderSources();};panel.querySelector('#focus-sources-next').onclick=()=>{page++;renderSources();};
    panel.querySelectorAll('[name=source_ids]').forEach(input=>input.onchange=()=>{if(input.checked && selected.size>=20){input.checked=false;errorMessage(new Error('Escolha até 20 fontes para este foco'));return;}if(input.checked)selected.add(input.value);else selected.delete(input.value);selectedSources();});
    selectedSources();ctx.bindDocuments();
  }
  if(docs.length){renderSources();panel.querySelector('#focus-source-query').oninput=event=>{query=event.target.value;page=0;renderSources();};}
  const form=panel.querySelector('#focus-form'),button=form.querySelector('[type=submit]');
  const fingerprint=()=>JSON.stringify({title:form.elements.title.value,source_ids:[...selected].sort()});
  let lastSaved=fingerprint(),saving=null;
  async function saveFocus(){
    if(saving){await saving;return saveFocus();}
    if(fingerprint()===lastSaved)return;
    const values={title:form.elements.title.value,source_ids:[...selected],expected_revision:focus.revision},pendingFingerprint=fingerprint();
    button.disabled=true;
    saving=(async()=>{
      try{
        const saved=await api('/api/focus',{method:'PUT',body:JSON.stringify(values)});
        focus.revision=saved.revision ?? saved.focus?.revision ?? focus.revision;lastSaved=pendingFingerprint;await refresh();
        if(form.isConnected)panel.querySelector('#focus-saved').textContent='Foco confirmado. Nenhuma tarefa foi criada e nenhum conteúdo foi enviado à IA.';
      }finally{saving=null;if(button.isConnected)button.disabled=false;}
    })();
    return saving;
  }
  form.onsubmit=async event=>{event.preventDefault();try{await saveFocus();}catch(error){errorMessage(error);}};
  return {save:saveFocus};

}

export async function renderTodayExperience(ctx) {
  const {api,esc,pageHead,state,navigate,taskCard,openTaskDialog,bindTaskActions,bindDocuments,errorMessage}=ctx;
  const experience=await api('/api/experience');
  if(state.view!=='today')return;
  const data=state.today,focus=experience.focus || {},docs=experience.sources || [];
  let focused=docs.filter(doc=>(focus.source_ids || []).includes(doc.id));
  for(const id of focus.source_ids || [])if(!focused.some(doc=>doc.id===id)){
    try{const doc=await api('/api/documents/'+encodeURIComponent(id));if(doc.active)focused.push(doc);}catch(_){/* Removed sources never block Today. */}
  }
  if(state.view!=='today')return;
  const panel=document.querySelector('#content'),count=experience.library?.active || 0;
  const sourceCard=doc=>'<article class="card source-card"><span class="badge">'+esc(doc.kind || 'fonte')+'</span><h3>'+esc(doc.title)+'</h3><p class="subtle">'+esc(doc.path || '')+'</p><p class="subtle">'+(doc.source_date?'Data da fonte: '+esc(doc.source_date):'Data original não informada')+'</p>'+(doc.evidence_excerpt?'<p class="kicker">TRECHO PARA CONFERIR</p><blockquote class="evidence-excerpt">'+esc(doc.evidence_excerpt)+'</blockquote><p class="subtle">Texto da fonte; autoria e atualidade precisam ser conferidas.</p>':'')+'<button class="btn" data-document="'+esc(doc.id)+'">Abrir fonte</button></article>';
  panel.innerHTML=pageHead('SEU TRABALHO, COM CONTINUIDADE','Hoje','<button class="btn" id="today-import">Trazer contexto</button>')+
    '<section class="card focus-hero"><p class="kicker">'+(focus.title?'FOCO CONFIRMADO POR VOCÊ':'COMEÇAR DE ONDE VOCÊ PAROU')+'</p><h2>'+esc(focus.title || 'O que vamos retomar?')+'</h2><p class="lede">'+(focus.title?'Abra as fontes que sustentam seu foco ou continue pensando com a Mia.':'Traga seu contexto e escolha o que continua em andamento. Nenhuma rotina, decisão ou pendência será inventada para preencher esta tela.')+'</p><div class="actions"><button class="btn primary" id="today-continue">'+(focus.title?'Conversar sobre meu foco':'Escolher meu foco')+'</button><button class="btn" id="today-focus">'+(focus.title?'Revisar foco':'Buscar nas fontes')+'</button></div>'+ (focus.unavailable_sources?'<p class="notice">'+Number(focus.unavailable_sources)+' fontes confirmadas estão pausadas ou indisponíveis. Reveja seu foco.</p>':'')+'</section>'+
    '<section class="section"><div class="section-head"><h2>'+(focused.length?'Fontes do meu foco':'Minha Biblioteca')+'</h2><button class="btn ghost" id="today-library">Ver Biblioteca</button></div>'+
    (count?'<p class="subtle">'+count+' fontes ativas. '+(focused.length?'Selecionadas por você para este foco.':'Abra um material reconhecível e escolha o que retomar.')+' Títulos e datas não confirmam decisões vigentes ou pendências.</p><div class="grid grid-3">'+(focused.length?focused.slice(0,6):docs.slice(0,6)).map(sourceCard).join('')+'</div>':'<div class="empty"><h3>Seu contexto ainda não chegou.</h3><p>Obsidian, Markdown e exports de conversas podem trazer a história do seu trabalho.</p><button class="btn primary" id="today-first-import">Trazer minhas fontes</button></div>')+'</section>'+
    (experience.migrations?.active || experience.migrations?.failed || experience.migrations?.partial?'<section class="card section"><h3>Minha migração</h3><p class="subtle">'+Number(experience.migrations.active || 0)+' importações em andamento ou aguardando revisão · '+Number(experience.migrations.failed || 0)+' com erros · '+Number(experience.migrations.partial || 0)+' concluídas com pendências. As fontes prontas já estão disponíveis; a cobertura pode ser parcial.</p><button class="btn" id="today-migration">Conferir cobertura</button></section>':'')+
    ((experience.threads || []).length?'<section class="section"><h2>Continuar uma conversa</h2><div class="list">'+experience.threads.slice(0,3).map(thread=>'<button class="thread-link" data-resume-thread="'+esc(thread.id)+'">'+esc(thread.title || 'Conversa')+'</button>').join('')+'</div></section>':'')+
    '<section class="section"><div class="section-head"><h2>Tarefas confirmadas</h2><button class="btn" data-open-task>+ Tarefa</button></div><div class="list">'+(data.tasks.length?data.tasks.map(taskCard).join(''):'<p class="subtle">Nenhuma tarefa aberta. Você pode retomar seu trabalho pelas fontes e conversas; não precisa cadastrar tarefas para começar.</p>')+'</div></section>'+locationCard(experience.location,esc,true)+ '<dialog class="dialog" id="focus-dialog"><div class="dialog-body"><button class="icon-btn" id="close-focus" aria-label="Fechar">×</button><div id="today-focus-panel"></div></div></dialog>';
  const focusDialog=panel.querySelector('#focus-dialog');
  async function editFocus(){await focusPanel(panel.querySelector('#today-focus-panel'),ctx,experience);focusDialog.showModal();}
  panel.querySelector('#today-continue').onclick=()=>focus.title?navigate('conversations',null,'Quero retomar este foco: '+focus.title):editFocus().catch(errorMessage);
  panel.querySelector('#today-focus').onclick=()=>focus.title?editFocus().catch(errorMessage):navigate('search');
  panel.querySelector('#close-focus').onclick=()=>{focusDialog.close();if(state.view==='today')renderTodayExperience(ctx).catch(errorMessage);};
  panel.querySelector('#today-import').onclick=()=>navigate('library');
  panel.querySelector('#today-first-import')?.addEventListener('click',()=>navigate('library'));
  panel.querySelector('#today-library').onclick=()=>navigate('library');
  panel.querySelector('#today-migration')?.addEventListener('click',()=>navigate('library'));
  panel.querySelectorAll('[data-resume-thread]').forEach(button=>button.onclick=()=>navigate('conversations',button.dataset.resumeThread));
  panel.querySelector('[data-open-task]').onclick=openTaskDialog;bindTaskActions();bindDocuments();
}
