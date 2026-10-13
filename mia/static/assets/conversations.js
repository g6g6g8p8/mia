// Conversation history is kept by this Mia installation, not in the browser.
const drafts = new Map();
let renderSequence=0;

export async function renderConversations(ctx, selectedId = null, initialMessage = '') {
  const sequence=++renderSequence;
  const {api, esc, pageHead, errorMessage, bindDocuments, refresh, state, navigate} = ctx;
  const panel = document.querySelector('#content');
  const [threads, settings] = await Promise.all([api('/api/conversations'), api('/api/ai/config')]);
  if (state.view !== 'conversations' || sequence!==renderSequence) return;
  const list = Array.isArray(threads) ? threads : threads.conversations;
  const active = selectedId ? await api('/api/conversations/' + encodeURIComponent(selectedId)) : null;
  if (state.view !== 'conversations' || sequence!==renderSequence) return;
  const runs = active?.runs || [];
  const cost = run => run.cost_status==='overrun' ? 'Uso excedeu o limite; novos pedidos bloqueados. Confira os limites em Ajustes.' : run.estimated_cost_usd != null ? 'Estimativa: US$ ' + esc(run.estimated_cost_usd)
    : run.cost_status === 'unknown' ? 'Custo desconhecido' : 'Custo não confirmado';
  function answerWithSources(text,sources){const known=new Map((sources || []).filter(source=>String(source.source).startsWith('doc:')).map(source=>[source.source,source]));return String(text || '').split(/(doc:[A-Za-z0-9_-]{8,100})/g).map(part=>{const source=known.get(part);return source?'<button class="inline-citation" data-document="'+esc(source.id || part.slice(4))+'" aria-label="Abrir fonte: '+esc(source.title || 'fonte')+'">'+esc(source.title || 'Abrir fonte')+'</button>':esc(part);}).join('');}
  const labels = {running:'Respondendo', awaiting_confirmation:'Proposta para revisar', completed:'Respondida', failed:'Pedido falhou', rejected:'Proposta recusada'};
  panel.innerHTML = pageHead('PENSAR E CONTINUAR', 'Conversas', '<button class="btn" id="conversation-new">Nova conversa</button>') +
    '<p class="lede">Converse com suas fontes. Cada pedido precisa da sua autorização; importar e buscar não usam IA.</p>' +
    '<div class="conversation-layout"><aside class="card conversation-list" aria-label="Suas conversas">' +
    (list.length ? list.map(thread => '<button class="thread-link '+(active?.id === thread.id?'selected':'')+'" data-thread="'+esc(thread.id)+'">'+esc(thread.title || 'Nova conversa')+'<span class="subtle">'+esc(thread.area_name || state.areas.find(area=>area.id===thread.area_id)?.name || 'Biblioteca autorizada')+'</span></button>').join('') : '<p class="subtle">Suas conversas aparecerão aqui.</p>') +
    '<details><summary>Escopo da próxima conversa</summary><label>Consultar<select id="conversation-area"><option value="">Toda a Biblioteca autorizada</option>'+state.areas.map(area=>'<option value="'+esc(area.id)+'">'+esc(area.name)+'</option>').join('')+'</select></label><p class="subtle">Conversas na Biblioteca respondem com fontes. Para propostas de tarefas, escolha uma área.</p></details></aside><section id="conversation-body">' + (active ?
      '<div class="section-head"><h2>'+esc(active.title || 'Nova conversa')+'</h2><button class="btn ghost" id="conversation-rename">Renomear</button></div>' +
      (active.scope_unavailable?'<p class="notice">A área desta conversa não está disponível. Histórico preservado; crie outra conversa para continuar.</p>':'')+'<p class="subtle">Escopo desta conversa: '+esc(active.area_name || state.areas.find(a=>a.id===active.area_id)?.name || 'fontes ativas da sua Biblioteca')+'. Fontes pausadas ficam fora dos novos pedidos.</p>' +
      (active.older_history_count?'<p class="subtle">Mostrando os últimos 100 pedidos. '+Number(active.older_history_count)+' anteriores permanecem guardados e exportáveis.</p>':'') +
      '<div class="list" id="conversation-messages">' + runs.map(run => {
        const proposal = run.proposal;
        return '<article class="card conversation-turn"><p class="kicker">SEU PEDIDO</p><p class="message-text">'+esc(run.request.message)+'</p><span class="badge">'+esc(labels[run.state] || run.state)+'</span>'+
          '<p class="message-text">'+answerWithSources(run.answer || run.error || 'Pedido em andamento. Você pode retornar a esta conversa.',run.sources)+'</p>' +
          (proposal ? '<section class="proposal"><h3>Proposta: '+esc(proposal.title)+'</h3><p class="message-text">'+esc(proposal.notes)+'</p>'+ (run.state==='awaiting_confirmation' ?
          '<form class="form" data-task-review="'+esc(run.id)+'"><label>Título<input name="title" required minlength="2" maxlength="200" value="'+esc(proposal.title)+'"></label><label>Notas<textarea name="notes" maxlength="10000">'+esc(proposal.notes)+'</textarea></label><div class="grid grid-2"><label>Data, se houver<input name="due_date" type="date" value="'+esc(proposal.due_date || '')+'"></label><label>Prioridade<select name="priority">'+[1,2,3].map(n=>'<option value="'+n+'" '+(n===proposal.priority?'selected':'')+'>'+['Baixa','Normal','Alta'][n-1]+'</option>').join('')+'</select></label></div><div class="actions"><button class="btn primary" type="submit">Confirmar e criar tarefa</button><button class="btn" type="button" data-reject="'+esc(run.id)+'">Recusar</button></div></form>' : '<p class="subtle">'+(run.task_result ? 'Tarefa confirmada: '+esc(run.task_result.title) : 'A proposta não cria uma tarefa sem confirmação.')+'</p>')+'</section>' : '') +
          '<details><summary>Fontes usadas neste pedido ('+(run.sources || []).length+')</summary><p class="subtle">Referências são evidência para conferir, não verificação automática da resposta.</p>'+ (run.sources || []).filter(s=>String(s.source).startsWith('doc:')).map(s=>'<button class="btn source-link" data-document="'+esc(s.id)+'">'+esc(s.title || s.source)+'</button>').join('') +'<pre class="source-preview">'+esc(JSON.stringify(run.sources || [], null, 2))+'</pre></details>'+
          ((run.invalid_citations || []).length ? '<p class="notice">Referências não reconhecidas: '+esc(run.invalid_citations.join(', '))+'</p>' : '') +
          (run.history_notice?'<p class="notice">'+esc(run.history_notice)+'</p>':'')+'<p class="subtle">'+cost(run)+' · Tokens: '+esc(run.usage?.total_tokens ?? 'não informados')+'</p></article>';
      }).join('') + '</div>' +
      '<section class="card section"><h3>Continuar esta conversa</h3>'+ (!settings.enabled ? '<p class="notice">IA desativada. Sua Biblioteca e a busca continuam disponíveis.</p><button class="btn" id="conversation-ai">Configurar IA opcional</button>' : '<p class="subtle">Destino: '+esc(settings.endpoint)+' · Modelo: '+esc(settings.model)+'. '+(settings.daily_budget_usd ? 'Limite diário estimado: US$ '+esc(settings.daily_budget_usd)+'.' : 'Custo monetário desconhecido; configure preços e orçamento se quiser um limite estimado.')+'</p>') +
      '<form class="form" id="conversation-form"><label>O que vamos retomar?<textarea name="message" required minlength="2" maxlength="4000" placeholder="Que decisão ficou registrada sobre este projeto?">'+esc(initialMessage)+'</textarea></label>'+
      '<label class="check-label"><input name="use_confirmed_focus" type="checkbox" '+(initialMessage?'checked':'')+'> Incluir meu foco e suas fontes confirmados neste pedido</label>'+
      '<label class="check-label"><input name="include_personal_context" type="checkbox"> Incluir Sobre mim e objetivo confirmados neste pedido</label>'+
      '<button class="btn" type="button" id="conversation-preview">Conferir contexto antes de enviar</button><div id="conversation-context" aria-live="polite"></div>'+
      '<label class="check-label"><input name="consent" type="checkbox" required> Autorizo enviar este pedido, trechos das fontes e histórico permitido ao destino acima.</label>'+
      '<button class="btn primary" type="submit" '+(!settings.enabled || active.scope_unavailable?'disabled':'')+'>Enviar pedido</button><p role="status" id="conversation-status"></p></form></section>'
      : '<section class="card welcome-card"><h2>Uma conversa, com continuidade.</h2><p class="lede">Escolha uma conversa ao lado ou abra uma nova. A Mia consulta apenas as fontes autorizadas e mantém o histórico nesta instalação.</p><button class="btn primary" id="conversation-start">Começar uma conversa</button><button class="btn ghost" id="conversation-search">Buscar sem IA</button></section>')+'</section></div>';

  async function create() {
    const thread = await api('/api/conversations', {method:'POST', body:JSON.stringify({title:'Nova conversa',area_id:panel.querySelector('#conversation-area')?.value || null})});
    await renderConversations(ctx, thread.id, initialMessage);
  }
  const safe = callback => async (...args) => {try {await callback(...args);} catch (error) {errorMessage(error);}};
  panel.querySelector('#conversation-new').onclick=safe(create);
  panel.querySelector('#conversation-start')?.addEventListener('click',safe(create));
  panel.querySelector('#conversation-search')?.addEventListener('click',()=>navigate('search'));
  panel.querySelectorAll('[data-thread]').forEach(button=>button.onclick=safe(()=>renderConversations(ctx,button.dataset.thread)));
  panel.querySelector('#conversation-ai')?.addEventListener('click',()=>navigate('ai-settings'));
  const form=panel.querySelector('#conversation-form');
  if (form) {
    panel.querySelector('#conversation-rename').onclick=safe(async()=>{
      const title=window.prompt('Nome desta conversa',active.title || '');
      if(title===null)return;
      if(!title.trim())throw new Error('Informe um nome para a conversa');
      await api('/api/conversations/'+active.id,{method:'PATCH',body:JSON.stringify({title:title.trim()})});
      await renderConversations(ctx,active.id);
    });
    panel.querySelector('#conversation-preview').onclick=safe(async()=>{
      const data=await api('/api/ai/context?thread_id='+encodeURIComponent(active.id)+'&q='+encodeURIComponent(form.elements.message.value)+'&include_personal_context='+form.elements.include_personal_context.checked+'&use_confirmed_focus='+form.elements.use_confirmed_focus.checked);
      if(!form.isConnected)return;
      panel.querySelector('#conversation-context').innerHTML='<p class="subtle">Confira os trechos. O histórico permitido desta conversa também pode acompanhar o pedido.</p><pre class="source-preview">'+esc(JSON.stringify(data,null,2))+'</pre>';
    });
    form.onsubmit=async event=>{
      event.preventDefault();
      const button=form.querySelector('[type=submit]'),status=form.querySelector('#conversation-status');
      const values={message:form.elements.message.value,thread_id:active.id,consent:form.elements.consent.checked,include_personal_context:form.elements.include_personal_context.checked,use_confirmed_focus:form.elements.use_confirmed_focus.checked};
      const fingerprint=JSON.stringify(values);
      let draft=drafts.get(active.id);
      if(!draft || draft.fingerprint!==fingerprint){draft={fingerprint,key:crypto.randomUUID()};drafts.set(active.id,draft);}
      button.disabled=true;status.textContent='Aguardando a resposta. Este pedido usa a mesma identificação se precisar tentar novamente.';
      try {
        await api('/api/runs',{method:'POST',body:JSON.stringify({...values,request_key:draft.key})});
        drafts.delete(active.id);await refresh();
        if(state.view==='conversations')await renderConversations(ctx,active.id);
      } catch(error) {errorMessage(error);status.textContent=error.message;button.disabled=!settings.enabled || active.scope_unavailable;}
    };
  }
  panel.querySelectorAll('[data-task-review]').forEach(review=>review.onsubmit=safe(async event=>{
    event.preventDefault();const button=review.querySelector('[type=submit]');button.disabled=true;
    const edits=Object.fromEntries(new FormData(review));edits.priority=Number(edits.priority);edits.due_date=edits.due_date || null;
    try{await api('/api/runs/'+review.dataset.taskReview+'/approve',{method:'POST',body:JSON.stringify({edits})});await refresh();await renderConversations(ctx,active.id);}finally{if(button.isConnected)button.disabled=false;}
  }));
  panel.querySelectorAll('[data-reject]').forEach(button=>button.onclick=safe(async()=>{
    button.disabled=true;try{await api('/api/runs/'+button.dataset.reject+'/reject',{method:'POST',body:'{}'});await renderConversations(ctx,active.id);}finally{if(button.isConnected)button.disabled=false;}
  }));
  bindDocuments();
}
