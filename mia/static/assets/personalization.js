export async function renderPersonalizationPage(ui, selectedArea) {
  const {state,api,esc,pageHead,bindDocuments,errorMessage,refresh}=ui;
  const [settings,docs,allRuns,current]=await Promise.all([api('/api/ai/config'),api('/api/documents'),api('/api/runs'),api('/api/personalization')]);
  if(state.view!=='personalization')return;
  const areaId=selectedArea||state.areas[0]?.id;
  const sources=docs.filter(d=>d.active&&d.area_id===areaId);
  const runs=allRuns.filter(r=>r.request.purpose==='personalization');
  const reload=()=>renderPersonalizationPage(ui,areaId);
  const labels={running:'Em andamento',awaiting_confirmation:'Aguardando sua revisão',completed:'Concluída',rejected:'Recusada',failed:'Falhou'};
  const fieldNames={context:'Contexto pessoal sugerido',goal:'Objetivo sugerido'};
  document.querySelector('#content').innerHTML=pageHead('CONHECIMENTO REVISADO','Meu contexto')+
    '<section class="card"><h2>O que você confirmou</h2><form class="form" id="context-edit"><label for="personal-current">Meu contexto pessoal</label><textarea id="personal-current" name="text" maxlength="1000">'+esc(current.text)+'</textarea><p class="subtle">Edite ou apague este resumo a qualquer momento. Em Inteligência, ele e seu objetivo só serão enviados se você marcar a opção de incluí-los. Pausar ou excluir fontes não apaga o resumo confirmado nem execuções antigas.</p><button class="btn" type="submit">Salvar meu contexto</button></form><p>Objetivo atual: '+esc(current.goal||'ainda não definido')+'</p></section>'+
    '<section class="card section"><h2>Sugestões a partir das suas fontes</h2><p class="subtle">Escolha até seis fontes ativas da mesma área. Serão enviados somente o pedido e o início de cada fonte, até 1.800 bytes por texto. Trechos podem ser incompletos ou antigos. Revise o que ainda faz sentido para você.</p><p>'+ (settings.enabled?esc(settings.model)+' · '+esc(settings.endpoint):'Configure sua IA em Sistema para gerar sugestões.')+'</p><p class="subtle">Uma chamada, com os mesmos limites de Inteligência: até '+settings.daily_call_limit+'/dia (UTC). '+(settings.daily_budget_usd?'Orçamento estimado: US$ '+esc(settings.daily_budget_usd)+'/dia.':'Custo desconhecido; nenhum orçamento monetário configurado.')+'</p>'+
    '<form class="form" id="personalization-form"><label for="personal-area">Área das fontes</label><select id="personal-area" name="area_id">'+state.areas.map(a=>'<option value="'+esc(a.id)+'" '+(a.id===areaId?'selected':'')+'>'+esc(a.name)+'</option>').join('')+'</select>'+
    (sources.length?sources.map(d=>'<label><span><input type="checkbox" name="source" value="'+esc(d.id)+'" style="width:auto"> '+esc(d.title)+' · '+esc(d.path)+'</span></label>').join(''):'<p>Nenhuma fonte ativa nesta área. Importe fontes ou escolha outra área.</p>')+
    '<label>O que deve orientar a sugestão? (opcional)<textarea name="message" maxlength="4000" placeholder="Ex.: resumir meu trabalho atual e sugerir um objetivo para revisar."></textarea></label><button class="btn" type="button" id="personal-preview">Ver trechos selecionados</button><pre id="personal-preview-text" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre>'+
    '<label><span><input type="checkbox" name="consent" required style="width:auto"> Autorizo enviar os trechos e meu pedido ao provedor acima.</span></label><button class="btn primary" type="submit" '+(!settings.enabled||!sources.length?'disabled':'')+'>Sugerir contexto e objetivo</button></form></section>'+
    '<section class="section"><h2>Sugestões para revisar</h2><p class="subtle">Os trechos abaixo existem nas fontes enviadas; isso não comprova a interpretação da IA. Confira autoria, atualidade e se o texto descreve você. Marque somente o que deseja aplicar. Confirmar substitui os campos selecionados e não cria tarefas.</p>'+runs.map(r=>{
      const proposal=r.proposal;
      return '<article class="card section"><span class="badge">'+esc(labels[r.state]||r.state)+'</span><p style="white-space:pre-wrap">'+esc(r.answer||r.error||'Atualize em alguns instantes.')+'</p>'+
        (proposal&&r.state==='awaiting_confirmation'?'<form class="form" data-personal-run="'+esc(r.id)+'">'+['context','goal'].filter(key=>proposal[key]).map(key=>'<fieldset data-personal-field="'+key+'"><legend>'+fieldNames[key]+'</legend><label><span><input type="checkbox" name="include" style="width:auto"> '+(key==='context'?'Aplicar este contexto':'Substituir meu objetivo atual')+'</span></label><label>Texto para revisar<textarea name="text" minlength="2" maxlength="1000">'+esc(proposal[key].text)+'</textarea></label>'+proposal[key].evidence.map(e=>'<blockquote style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(e.quote)+'</blockquote><button class="btn" type="button" data-document="'+esc(e.document_id)+'">Abrir fonte de apoio</button>').join('')+'</fieldset>').join('')+'<button class="btn primary" type="submit">Confirmar personalização selecionada</button><button class="btn" type="button" data-personal-reject="'+esc(r.id)+'">Recusar personalização</button></form>':'')+
        (r.personalization_result?'<p>Personalização aplicada. Campos confirmados: '+Object.entries(r.personalization_result.accepted_plan).filter(([,value])=>value).map(([key])=>key==='context'?'contexto':'objetivo').join(', ')+'.</p>':'')+
        '<details><summary>Registro desta proposta</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(JSON.stringify({proposal:r.proposal,applied:r.personalization_result,sources:r.sources},null,2))+'</pre></details><p class="subtle">'+(r.estimated_cost_usd!==null?'Custo estimado US$ '+r.estimated_cost_usd:r.cost_status==='unknown'?'Custo desconhecido':r.cost_status==='overrun'?'Uso excedeu limites; novas chamadas bloqueadas':'Custo não confirmado; reserva US$ '+r.reserved_usd)+'</p></article>';
    }).join('')+'</section>';
  document.querySelector('#context-edit').onsubmit=async event=>{
    event.preventDefault();const form=event.currentTarget,button=form.querySelector('button');button.disabled=true;
    try{await api('/api/personalization',{method:'PUT',body:JSON.stringify({text:form.elements.text.value,expected_revision:current.revision})});await reload();}catch(error){errorMessage(error);button.disabled=false;}
  };
  const form=document.querySelector('#personalization-form');
  form.elements.area_id.onchange=()=>renderPersonalizationPage(ui,form.elements.area_id.value).catch(errorMessage);
  const selection=()=>({area_id:form.elements.area_id.value,document_ids:[...form.querySelectorAll('[name=source]:checked')].map(input=>input.value)});
  form.querySelector('#personal-preview').onclick=async()=>{try{const preview=await api('/api/organization/preview',{method:'POST',body:JSON.stringify(selection())});if(form.isConnected)form.querySelector('#personal-preview-text').textContent=JSON.stringify(preview,null,2);}catch(error){errorMessage(error);}};
  let key=crypto.randomUUID(),previous='';
  form.onsubmit=async event=>{
    event.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;
    const values={...selection(),purpose:'personalization',message:form.elements.message.value.trim()||'Sugira um contexto pessoal e um objetivo apoiados nas fontes selecionadas, para eu revisar.',consent:form.elements.consent.checked};
    const fingerprint=JSON.stringify(values);if(previous&&previous!==fingerprint)key=crypto.randomUUID();previous=fingerprint;
    try{await api('/api/runs',{method:'POST',body:JSON.stringify({...values,request_key:key})});await reload();}catch(error){errorMessage(error);button.disabled=false;}
  };
  document.querySelectorAll('[data-personal-run]').forEach(form=>form.onsubmit=async event=>{
    event.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;
    const original=runs.find(r=>r.id===form.dataset.personalRun).proposal;
    const accepted={context:null,goal:null};
    for(const field of form.querySelectorAll('[data-personal-field]'))if(field.querySelector('[name=include]').checked){const name=field.dataset.personalField;accepted[name]={...original[name],text:field.querySelector('[name=text]').value};}
    try{if(!accepted.context&&!accepted.goal)throw new Error('Selecione contexto ou objetivo para aplicar');await api('/api/runs/'+form.dataset.personalRun+'/personalization/approve',{method:'POST',body:JSON.stringify(accepted)});state.onboarding=await api('/api/onboarding');await refresh();await reload();}catch(error){errorMessage(error);button.disabled=false;}
  });
  document.querySelectorAll('[data-personal-reject]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await api('/api/runs/'+button.dataset.personalReject+'/reject',{method:'POST',body:'{}'});await reload();}catch(error){errorMessage(error);button.disabled=false;}});
  bindDocuments();
}
