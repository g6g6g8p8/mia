const app = document.querySelector("#app");
const toast = document.querySelector("#toast");
let state = { view: "today", owner: null, areas: [], today: null, onboarding: null };

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function (character) {
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[character];
  });
}

function localDate(value) {
  return value ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(new Date(value + "T12:00:00")) : "";
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(function () { toast.classList.remove("show"); }, 2400);
}

async function api(path, options) {
  options = options || {};
  const response = await fetch(path, Object.assign({
    credentials: "same-origin",
    headers: Object.assign({ "Content-Type": "application/json" }, options.headers || {})
  }, options));
  if (response.status === 401) {
    renderLogin();
    throw new Error("Entre para continuar");
  }
  const isJson = (response.headers.get("content-type") || "").includes("json");
  const data = isJson ? await response.json() : null;
  if (!response.ok) {
    const detail = data && data.detail;
    throw new Error(Array.isArray(detail) ? detail.map(item=>item.msg).join('; ') : detail || "Não foi possível concluir");
  }
  return data;
}

function errorMessage(error) {
  showToast(error instanceof Error ? error.message : "Não foi possível concluir");
}

async function boot() {
  try {
    const status = await api("/api/status");
    if (!status.configured) {
      renderSetup();
      return;
    }
    state.owner = await api("/api/me");
    await refresh();
    state.onboarding = await api('/api/onboarding');
    if (!state.onboarding.completed) state.view = 'onboarding';
    renderShell();
  } catch (error) {
    if (error.message !== "Entre para continuar") errorMessage(error);
  }
}

function renderSetup() {
  app.innerHTML =
    '<main class="auth"><section class="card auth-card">' +
    '<img src="/assets/mia-icon.svg" class="auth-logo" alt="Gatinha da Mia">' +
    '<p class="kicker">PRIMEIRO ACESSO</p><h1>Sua Mia começa vazia.</h1>' +
    '<p class="lede">Crie o acesso local e a primeira área. Nenhuma conta externa é necessária.</p>' +
    '<div class="steps"><span class="step on"></span><span class="step on"></span><span class="step on"></span></div>' +
    '<form id="setup-form" class="form">' +
    '<div class="grid grid-2"><label>Seu nome<input name="name" required minlength="2" autocomplete="name"></label>' +
    '<label>E-mail opcional<input name="email" type="email" autocomplete="email"></label></div>' +
    '<label>Fuso horário<input name="timezone" value="America/Sao_Paulo" required></label>' +
    '<label>Senha local<input name="password" type="password" required minlength="10" autocomplete="new-password"><span class="subtle">Use pelo menos 10 caracteres.</span></label>' +
    '<label>Primeira área<input name="area_name" required minlength="2" placeholder="Ex.: Trabalho, Clientes, Estudos"></label>' +
    '<label>O que pertence a essa área?<textarea name="area_description" placeholder="Uma descrição curta ajuda a manter o contexto organizado."></textarea></label>' +
    '<button class="btn primary" type="submit">Criar minha Mia</button></form></section></main>';
  document.querySelector("#setup-form").addEventListener("submit", async function (event) {
    event.preventDefault();
    try {
      await api("/api/setup", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) });
      await boot();
    } catch (error) { errorMessage(error); }
  });
}

function renderLogin() {
  app.innerHTML =
    '<main class="auth"><section class="card auth-card">' +
    '<img src="/assets/mia-icon.svg" class="auth-logo" alt="Gatinha da Mia">' +
    '<p class="kicker">BEM-VINDO DE VOLTA</p><h1>Entre na sua Mia.</h1>' +
    '<p class="lede">O acesso é validado nesta instalação.</p>' +
    '<form id="login-form" class="form"><label>Senha<input name="password" type="password" required autocomplete="current-password" autofocus></label>' +
    '<button class="btn primary" type="submit">Entrar</button></form></section></main>';
  document.querySelector("#login-form").addEventListener("submit", async function (event) {
    event.preventDefault();
    try {
      await api("/api/login", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) });
      await boot();
    } catch (error) { errorMessage(error); }
  });
}

async function refresh() {
  const results = await Promise.all([api("/api/today"), api("/api/areas")]);
  state.today = results[0];
  state.areas = results[1];
}

function dialogs() {
  const areaOptions = state.areas.map(function (area) {
    return '<option value="' + esc(area.id) + '">' + esc(area.name) + '</option>';
  }).join("");
  return '<dialog class="dialog" id="task-dialog"><div class="dialog-body">' +
    '<div class="dialog-head"><div><p class="kicker">NOVA AÇÃO</p><h2>Criar tarefa</h2></div><button class="icon-btn" data-close="#task-dialog" aria-label="Fechar">×</button></div>' +
    '<form class="form" id="task-form"><label>Título<input name="title" required minlength="2"></label>' +
    '<div class="grid grid-2"><label>Área<select name="area_id"><option value="">Sem área</option>' + areaOptions + '</select></label>' +
    '<label>Data<input type="date" name="due_date"></label></div>' +
    '<label>Prioridade<select name="priority"><option value="1">Baixa</option><option value="2" selected>Normal</option><option value="3">Alta</option></select></label>' +
    '<label>Notas<textarea name="notes"></textarea></label><button class="btn primary" type="submit">Criar tarefa</button></form></div></dialog>' +
    '<dialog class="dialog" id="area-dialog"><div class="dialog-body">' +
    '<div class="dialog-head"><div><p class="kicker">NOVO CONTEXTO</p><h2>Criar área</h2></div><button class="icon-btn" data-close="#area-dialog" aria-label="Fechar">×</button></div>' +
    '<form class="form" id="area-form"><label>Nome<input name="name" required minlength="2"></label>' +
    '<label>Descrição<textarea name="description"></textarea></label>' +
    '<label>Cor<select name="color"><option value="slate">Grafite</option><option value="violet">Violeta</option><option value="blue">Azul</option><option value="green">Verde</option><option value="amber">Âmbar</option><option value="rose">Rosa</option></select></label>' +
    '<button class="btn primary" type="submit">Criar área</button></form></div></dialog>';
}

function renderShell() {
  app.innerHTML =
    '<div class="shell"><aside class="sidebar"><div class="brand">' +
    '<img src="/assets/mia-icon.svg" alt=""><div><div class="brand-name">Mia</div><div class="brand-tag">central de comando</div></div></div>' +
    '<nav class="nav" aria-label="Principal"><button data-view="today">Hoje</button><button data-view="areas">Áreas</button>' +
    '<button data-view="search">Busca</button><button data-view="intelligence">Inteligência</button><button data-view="system">Sistema</button></nav>' +
    '<div class="sidebar-foot"><span class="subtle">' + esc(state.owner.name) + '</span><button class="btn ghost" id="logout">Sair</button></div>' +
    '</aside><main class="content" id="content"></main></div>' + dialogs();
  document.querySelectorAll("[data-view]").forEach(function (button) {
    button.addEventListener("click", function () { navigate(button.dataset.view); });
  });
  document.querySelector("#logout").addEventListener("click", async function () {
    await api("/api/logout", { method: "POST", body: "{}" });
    renderLogin();
  });
  document.querySelector("#task-form").addEventListener("submit", submitTask);
  document.querySelector("#area-form").addEventListener("submit", submitArea);
  document.querySelectorAll("[data-close]").forEach(function (button) {
    button.addEventListener("click", function () { document.querySelector(button.dataset.close).close(); });
  });
  navigate(state.view);
}

function navigate(view) {
  state.view = view;
  document.querySelectorAll("[data-view]").forEach(function (button) {
    button.classList.toggle("active", button.dataset.view === view);
  });
  if (view === "today") renderToday();
  if (view === "areas") renderAreas();
  if (view === "search") renderSearch();
  if (view === "system") renderSystem();
  if (view === "intelligence") renderIntelligence().catch(errorMessage);
  if (view === "onboarding") renderGuide().catch(errorMessage);
  if (view === "knowledge") renderKnowledge().catch(errorMessage);
  if (view === "ai-settings") renderAISettings().catch(errorMessage);
}

function pageHead(kicker, title, action) {
  return '<header class="page-head"><div><p class="kicker">' + kicker + '</p><h1>' + title + '</h1></div>' + (action || "") + '</header>';
}

function taskCard(task) {
  const today = state.today.date;
  const overdue = task.due_date && task.due_date < today;
  return '<article class="task"><button class="check" data-done="' + esc(task.id) + '" aria-label="Concluir tarefa">✓</button>' +
    '<div><div class="task-title">' + esc(task.title) + '</div><div class="task-meta">' +
    (task.area_name ? esc(task.area_name) : "Sem área") + (task.due_date ? " · " + localDate(task.due_date) : "") + '</div></div>' +
    '<span class="badge ' + (overdue ? "overdue" : task.priority === 3 ? "high" : "") + '">' +
    (overdue ? "atrasada" : task.priority === 3 ? "alta" : "aberta") + '</span></article>';
}

function bindTaskActions() {
  document.querySelectorAll("[data-done]").forEach(function (button) {
    button.addEventListener("click", async function () {
      try {
        await api("/api/tasks/" + button.dataset.done, { method: "PATCH", body: JSON.stringify({ status: "done" }) });
        await refresh();
        navigate(state.view);
        showToast("Tarefa concluída");
      } catch (error) { errorMessage(error); }
    });
  });
}

function areaCard(area) {
  return '<article class="card area"><h3><span class="dot ' + esc(area.color) + '"></span>' + esc(area.name) + '</h3>' +
    '<p class="subtle">' + esc(area.description || "Sem descrição") + '</p><div class="area-count">' +
    area.open_tasks + " tarefa" + (area.open_tasks == 1 ? "" : "s") + " aberta" + (area.open_tasks == 1 ? "" : "s") + '</div></article>';
}

function renderToday() {
  const data = state.today;
  const longDate = new Intl.DateTimeFormat("pt-BR", { dateStyle: "full" }).format(new Date(data.date + "T12:00:00"));
  document.querySelector("#content").innerHTML =
    pageHead("AGORA · " + longDate, "Bom dia, " + esc(data.owner.name.split(" ")[0]) + ".", '<button class="btn primary" data-open-task>+ Tarefa</button>') +
    (state.onboarding?.goal?'<section class="card"><p class="kicker">SEU OBJETIVO DECLARADO</p><p>'+esc(state.onboarding.goal)+'</p></section><div style="height:16px"></div>':'')+
    '<section class="grid grid-3"><div class="card metric"><strong>' + data.tasks.length + '</strong><span>tarefas em foco</span></div>' +
    '<div class="card metric"><strong>' + data.due_today + '</strong><span>para hoje</span></div>' +
    '<div class="card metric"><strong>' + data.overdue + '</strong><span>atrasadas</span></div></section>' +
    '<section class="section"><div class="section-head"><h2>O que pede atenção</h2><span class="subtle">regras locais · sem IA</span></div><div class="list">' +
    (data.tasks.length ? data.tasks.map(taskCard).join("") : '<div class="empty">Nada exige atenção agora.<br>Crie uma tarefa quando houver algo concreto.</div>') +
    '</div></section><section class="section"><div class="section-head"><h2>Áreas</h2></div><div class="grid grid-3">' +
    data.areas.map(areaCard).join("") + '</div></section>';
  document.querySelector("[data-open-task]").addEventListener("click", openTaskDialog);
  bindTaskActions();
}

function renderAreas() {
  document.querySelector("#content").innerHTML =
    pageHead("SEUS CONTEXTOS", "Áreas", '<div><button class="btn" id="open-knowledge">Fontes</button> <button class="btn primary" data-open-area>+ Área</button></div>') +
    '<p class="lede">Cada área delimita um contexto. A instalação começou vazia e mostra somente o que você criou.</p>' +
    '<section class="section grid grid-3">' + state.areas.map(areaCard).join("") + '</section>';
  document.querySelector("[data-open-area]").addEventListener("click", function () {
    document.querySelector("#area-dialog").showModal();
  });
  document.querySelector('#open-knowledge').onclick=()=>navigate('knowledge');
}

function renderSearch() {
  document.querySelector("#content").innerHTML =
    pageHead("EVIDÊNCIA LOCAL", "Busca") +
    '<input class="search" id="search-input" placeholder="Busque tarefas e áreas…" autofocus>' +
    '<section class="card section" id="results"><div class="empty">Digite pelo menos dois caracteres.</div></section>';
  let timer;
  document.querySelector("#search-input").addEventListener("input", function (event) {
    window.clearTimeout(timer);
    const input = event.target;
    if (input.value.trim().length < 2) {
      document.querySelector('#results').innerHTML='<div class="empty">Digite pelo menos dois caracteres.</div>';
      return;
    }
    timer = window.setTimeout(async function () {
      const query = input.value.trim();
      if (query.length < 2) return;
      try {
        const data = await api("/api/search?q=" + encodeURIComponent(query));
        if (state.view !== 'search' || input.value.trim() !== query || !input.isConnected) return;
        document.querySelector("#results").innerHTML = data.results.length ? data.results.map(function (result) {
          return '<article class="result"><span class="badge">' + esc(result.type === "task" ? "tarefa" : result.type === 'document' ? 'fonte' : "área") + '</span>' +
            '<h3 style="margin-top:10px">' + esc(result.title) + '</h3><p class="subtle">' + esc(result.notes || "") + '</p>' +
            '<div class="task-meta">' + esc(result.area_name || "") + (result.due_date ? " · " + localDate(result.due_date) : "") + '</div>'+(result.type==='document'?'<button class="btn" data-document="'+esc(result.id)+'">Abrir fonte</button>':'')+'</article>';
        }).join("") : '<div class="empty">Nenhum resultado.</div>';
        bindDocuments();
      } catch (error) { errorMessage(error); }
    }, 220);
  });
}

function renderSystem() {
  document.querySelector("#content").innerHTML =
    pageHead("CONTROLE LOCAL", "Sistema") +
    '<section class="grid grid-2"><article class="card"><p class="kicker">IDENTIDADE</p><h2>' + esc(state.owner.name) + '</h2>' +
    '<p class="subtle">' + esc(state.owner.email || "Sem e-mail") + " · " + esc(state.owner.timezone) + '</p></article>' +
    '<article class="card"><p class="kicker">INTELIGÊNCIA</p><h2>IA opcional</h2><p class="subtle">Hoje usa regras locais. Consulte Inteligência para ver o provedor configurado nesta instalação.</p></article>' +
    '<article class="card"><p class="kicker">DADOS</p><h2>Exportação aberta</h2><p class="subtle">Baixe suas áreas e tarefas em JSON dentro de um ZIP.</p>' +
    '<a class="btn" style="display:inline-block;margin-top:14px;text-decoration:none" href="/api/export">Exportar dados</a></article>' +
    '<article class="card"><p class="kicker">CONFIGURAÇÃO</p><h2>Sua instalação</h2><p class="subtle">Retome a preparação, traga fontes ou configure seu modelo.</p><button class="btn" id="resume-guide">Onboarding</button> <button class="btn" id="system-sources">Fontes</button> <button class="btn" id="system-ai">Configurar IA</button></article></section>';
  document.querySelector('#resume-guide').onclick=()=>navigate('onboarding');
  document.querySelector('#system-sources').onclick=()=>navigate('knowledge');
  document.querySelector('#system-ai').onclick=()=>navigate('ai-settings');
}

async function renderIntelligence() {
  const [settings, runs] = await Promise.all([api("/api/ai/config"), api("/api/runs")]);
  if (state.view !== "intelligence") return;
  const labels = {running:"Em andamento",awaiting_confirmation:"Aguardando confirmação",completed:"Concluída",failed:"Falhou",rejected:"Recusada"};
  document.querySelector("#content").innerHTML = pageHead("CONTEXTO E AÇÃO", "Inteligência") +
    '<section class="card"><p class="lede">' + (settings.enabled ? esc(settings.model) + ' · ' + esc(settings.endpoint) : 'IA desativada. Configure seu modelo em Sistema ou continue usando a busca local.') + '</p>' +
    '<p class="subtle">Até ' + settings.daily_call_limit + ' chamadas/dia (UTC), 1.000 tokens de saída e 45 segundos. '+(settings.daily_budget_usd?'Orçamento estimado: US$ '+esc(settings.daily_budget_usd)+'/dia.':'Custo desconhecido; nenhum orçamento monetário configurado.')+' Defina também um limite no provedor.</p>' +
    '<form class="form" id="run-form"><label>Área autorizada<select name="area_id">' + state.areas.map(a=>'<option value="'+esc(a.id)+'">'+esc(a.name)+'</option>').join('') + '</select></label>' +
    '<button type="button" class="btn" id="preview-context">Ver contexto que será enviado</button><pre id="context-preview" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre>' +
    '<label>Seu pedido<textarea name="message" required minlength="2" maxlength="4000" placeholder="O que merece atenção nesta área? Ou: proponha uma tarefa para amanhã."></textarea></label>' +
    '<label><input type="checkbox" name="consent" required style="width:auto"> Autorizo enviar este pedido e o contexto da área ao provedor mostrado acima.</label>' +
    '<p class="subtle">Até 12 tarefas e 3 trechos de fontes da área encontrados pelo seu pedido. Não envia outras áreas, e-mail ou senhas. Pedidos independentes.</p>' +
    '<button class="btn primary" type="submit" '+(!settings.enabled?'disabled':'')+'>Enviar pedido</button></form></section>' +
    '<section class="section"><h2>Execuções recentes</h2>' + runs.map(r=>{
      const p=r.proposal;
      return '<article class="card section"><span class="badge">'+esc(labels[r.state]||r.state)+'</span><h3>'+esc(r.request.message)+'</h3>' +
        '<p style="white-space:pre-wrap">'+esc(r.answer||r.error||'Aguardando resposta. Atualize esta aba em alguns instantes.')+'</p>' +
        (p?'<div class="card"><h3>Proposta: '+esc(p.title)+'</h3><p>'+esc(p.notes)+'</p><p>Data: '+esc(p.due_date||'sem data')+' · Prioridade: '+p.priority+'</p>'+
        (r.state==='awaiting_confirmation'?'<button class="btn primary" data-decision="approve" data-run="'+esc(r.id)+'">Confirmar e criar tarefa</button> <button class="btn" data-decision="reject" data-run="'+esc(r.id)+'">Recusar</button>':'')+'</div>':'') +
        '<details><summary>Contexto enviado · '+r.sources.length+' fontes (não é verificação automática da resposta)</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(JSON.stringify(r.sources,null,2))+'</pre></details>' +
        '<p class="subtle">Tokens: '+esc(r.usage?.total_tokens??'não informado')+' · '+(r.estimated_cost_usd!==null?'Custo estimado US$ '+r.estimated_cost_usd:r.cost_status==='unknown'?'Custo desconhecido':r.cost_status==='overrun'?'Uso excedeu os limites; novas chamadas bloqueadas':'Custo não confirmado; reserva US$ '+r.reserved_usd)+'</p>'+
        (r.invalid_citations.length?'<p class="subtle">Referências não reconhecidas: '+esc(r.invalid_citations.join(', '))+'</p>':'')+
        r.sources.filter(s=>s.source.startsWith('doc:')).map(s=>'<button class="btn" data-document="'+esc(s.id)+'">Abrir '+esc(s.title)+'</button>').join('')+'</article>';
    }).join('')+'</section>';
  const form=document.querySelector('#run-form');
  document.querySelector('#preview-context').onclick=async()=>{
    try { const data=await api('/api/ai/context?area_id='+encodeURIComponent(form.elements.area_id.value)+'&q='+encodeURIComponent(form.elements.message.value));
      const preview=document.querySelector('#context-preview'); if(preview) preview.textContent=JSON.stringify(data,null,2);
    } catch(error){errorMessage(error);}
  };
  form.onsubmit=async event=>{
    event.preventDefault();
    const button=form.querySelector('[type=submit]'); button.disabled=true; button.textContent='Processando…';
    const values={message:form.elements.message.value,area_id:form.elements.area_id.value,consent:form.elements.consent.checked,request_key:crypto.randomUUID()};
    try { await api('/api/runs',{method:'POST',body:JSON.stringify(values)}); await renderIntelligence(); }
    catch(error){errorMessage(error); button.disabled=false; button.textContent='Enviar pedido';}
  };
  document.querySelectorAll('[data-decision]').forEach(button=>button.onclick=async()=>{
    button.disabled=true;
    try { await api('/api/runs/'+button.dataset.run+'/'+button.dataset.decision,{method:'POST',body:'{}'}); await refresh(); await renderIntelligence(); }
    catch(error){errorMessage(error);button.disabled=false;}
  });
  bindDocuments();
}

function bindDocuments(){
  document.querySelectorAll('[data-document]').forEach(button=>button.onclick=async()=>{
    try {
      const doc=await api('/api/documents/'+button.dataset.document);
      const prior=document.querySelector('#source-dialog'); if(prior) prior.remove();
      const dialog=document.createElement('dialog'); dialog.id='source-dialog';dialog.className='dialog';
      dialog.innerHTML='<div class="dialog-body"><h2>'+esc(doc.title)+'</h2><p class="subtle">'+esc(doc.kind)+' · '+esc(doc.path)+' · Importado em '+esc(doc.created_at)+' · '+(doc.active?'Ativa':'Pausada — fora de novas consultas')+'</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(doc.content)+'</pre><button class="btn" id="close-source">Fechar fonte</button></div>';
      document.body.append(dialog); dialog.showModal(); dialog.querySelector('#close-source').onclick=()=>dialog.close();
    }catch(error){errorMessage(error);}
  });
}

async function saveGuide(step,completed=false){
  state.onboarding=await api('/api/onboarding',{method:'PUT',body:JSON.stringify({goal:state.onboarding.goal,step,completed})});
}

async function renderGuide(){
  state.onboarding=await api('/api/onboarding');
  if(state.view!=='onboarding')return;
  const step=state.onboarding.step;
  const titles=['O que você quer resolver primeiro?','Traga seu conhecimento.','Escolha como usar a IA.','Comece com algo seu.'];
  document.querySelector('#content').innerHTML=pageHead('PREPARAR SUA MIA · '+(step+1)+' DE 4',titles[step])+ '<section class="card" id="guide-body"></section><div class="section"><button class="btn" id="guide-back" '+(step===0?'disabled':'')+'>Voltar</button> <button class="btn primary" id="guide-next">'+(step===3?'Concluir preparação':'Continuar')+'</button> <button class="btn ghost" id="guide-skip">Ir para Hoje</button></div>';
  const body=document.querySelector('#guide-body');
  if(step===0)body.innerHTML='<p class="lede">Conte um objetivo atual. Você pode alterá-lo depois. Nenhuma tarefa será criada automaticamente.</p><label>Seu primeiro objetivo<textarea id="guide-goal" maxlength="1000" placeholder="Ex.: organizar decisões e próximos passos de um projeto.">'+esc(state.onboarding.goal)+'</textarea></label>';
  if(step===1){body.innerHTML='<p class="lede">Importe notas ou conversas e selecione o que a Mia pode consultar. Também pode continuar sem importar.</p><div id="knowledge-panel"></div>';await knowledgePanel(document.querySelector('#knowledge-panel'));}
  if(step===2){body.innerHTML='<p class="lede">Use seu provedor e chave ou continue sem IA. Salvar a configuração não faz uma chamada.</p><div id="ai-panel"></div>';await aiPanel(document.querySelector('#ai-panel'));}
  if(step===3){const docs=(await api('/api/documents')).filter(d=>d.active);body.innerHTML='<p class="lede">'+docs.length+' fontes disponíveis. Seu objetivo: '+esc(state.onboarding.goal||'ainda não informado')+'.</p><p>Use a busca para encontrar uma informação nas suas fontes. Com IA configurada, faça uma pergunta em Inteligência e confira as referências.</p><button class="btn" id="first-search">Buscar nas minhas fontes</button> <button class="btn" id="first-ai">Fazer uma pergunta</button>';body.querySelector('#first-search').onclick=async()=>{await saveGuide(3,true);navigate('search');};body.querySelector('#first-ai').onclick=async()=>{await saveGuide(3,true);navigate('intelligence');};}
  if(state.view!=='onboarding'||!body.isConnected)return;
  document.querySelector('#guide-back').onclick=async()=>{await saveGuide(Math.max(0,step-1));await renderGuide();};
  document.querySelector('#guide-next').onclick=async()=>{try{if(step===0)state.onboarding.goal=document.querySelector('#guide-goal').value;await saveGuide(Math.min(3,step+1),step===3);if(step===3)navigate('today');else await renderGuide();}catch(error){errorMessage(error);}};
  document.querySelector('#guide-skip').onclick=async()=>{if(step===0)state.onboarding.goal=document.querySelector('#guide-goal').value;await saveGuide(step,true);navigate('today');};
}

async function renderKnowledge(){
  document.querySelector('#content').innerHTML=pageHead('FONTES LOCAIS','Seu conhecimento')+'<section class="card" id="knowledge-panel"></section>';
  await knowledgePanel(document.querySelector('#knowledge-panel'));
}

async function knowledgePanel(panel){
  const [batches,docs]=await Promise.all([api('/api/imports'),api('/api/documents')]);
  if(!panel.isConnected)return;
  panel.innerHTML='<p class="subtle">Markdown, texto, ZIP de vault e JSON de conversas reconhecido (experimental). Até 8 MB por upload, 20 MB expandido, 300 entradas e 500 documentos. PDF, mídia, anexos e configurações de conta são ignorados. Nada é enviado a uma IA ao importar.</p>'+
    '<form id="import-form" class="form"><label>Área de destino<select name="area_id">'+state.areas.map(a=>'<option value="'+esc(a.id)+'">'+esc(a.name)+'</option>').join('')+'</select></label><label>Escolher arquivo<input name="file" type="file" accept=".md,.txt,.zip,.json" required></label><button class="btn primary" type="submit">Preparar importação</button></form>'+
    '<details class="section"><summary>Ou colar uma nota</summary><form id="paste-form" class="form"><label>Título<input name="title" maxlength="150" required></label><label>Conteúdo<textarea name="content" required maxlength="200000"></textarea></label><button class="btn" type="submit">Revisar nota</button></form></details>'+
    '<section class="section">'+batches.map(batch=>'<article class="card section"><h3>'+esc(batch.name)+'</h3><p>'+esc(batch.state==='review'?'Aguardando sua revisão':'Importação concluída')+'</p>'+
    (batch.state==='review'?'<form data-batch="'+esc(batch.id)+'"><p>Selecione o que deve ficar disponível. Versões diferentes são mantidas separadamente; pause as antigas na lista de fontes.</p>'+batch.items.map(item=>'<article class="card" style="margin:8px 0"><label><span><input type="checkbox" name="item" value="'+esc(item.id)+'" style="width:auto"> '+esc(item.title)+' · '+esc(item.kind)+'</span><span class="subtle">'+esc(item.path)+' · '+item.characters+' caracteres</span></label>'+(item.duplicates.length?'<p>Conteúdo já importado. Confirmar preserva a fonte existente e seu estado atual.</p>':'')+(item.conflicts.length?'<p>Mesmo caminho, conteúdo diferente. Nenhuma versão será substituída.</p>'+item.conflicts.map(d=>'<button type="button" class="btn" data-document="'+esc(d.id)+'">Comparar com '+esc(d.title)+(d.active?'':' (pausada)')+'</button>').join(''):'')+'<details><summary>Prévia</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(item.preview)+'</pre></details></article>').join('')+'<button class="btn primary" type="submit">Confirmar selecionados</button></form>':'<p>'+esc(batch.report.imported)+' novos · '+esc(batch.report.duplicates)+' duplicados · '+esc(batch.report.not_selected)+' não selecionados</p>')+
    '<details><summary>Relatório e limitações</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(JSON.stringify(batch.report,null,2))+'</pre></details><button class="btn ghost" data-remove-import="'+esc(batch.id)+'">'+(batch.state==='review'?'Cancelar lote':'Excluir lote e suas fontes')+'</button></article>').join('')+'</section><section class="section"><h3>Fontes disponíveis ('+docs.filter(d=>d.active).length+')</h3><p class="subtle">Fontes pausadas continuam guardadas e exportáveis, mas não entram na busca nem em novas consultas. Execuções antigas mantêm o contexto registrado.</p>'+docs.map(d=>'<article class="card section"><button class="btn" data-document="'+esc(d.id)+'">'+esc(d.title)+'</button><p class="subtle">'+esc(d.path)+' · '+esc(state.areas.find(a=>a.id===d.area_id)?.name||'')+' · '+esc(d.created_at)+' · '+(d.active?'Ativa':'Pausada')+'</p><button class="btn" data-source-state="'+esc(d.id)+'" data-active="'+(d.active?'false':'true')+'">'+(d.active?'Pausar fonte':'Reativar fonte')+'</button></article>').join('')+'</section>';
  async function prepare(file){
    if(file.size>8*1024*1024)throw new Error('Arquivo excede 8 MB');
    const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});
    await api('/api/imports',{method:'POST',body:JSON.stringify({area_id:panel.querySelector('#import-form select').value,filename:file.name,content_base64:encoded})});
    await knowledgePanel(panel);
  }
  panel.querySelector('#import-form').onsubmit=async event=>{event.preventDefault();const form=event.currentTarget;const button=form.querySelector('button');button.disabled=true;try{await prepare(form.elements.file.files[0]);}catch(error){errorMessage(error);button.disabled=false;}};
  panel.querySelector('#paste-form').onsubmit=async event=>{event.preventDefault();const form=event.currentTarget;try{await prepare(new File(['# '+form.elements.title.value+'\n\n'+form.elements.content.value],'nota.md',{type:'text/markdown'}));}catch(error){errorMessage(error);}};
  panel.querySelectorAll('[data-batch]').forEach(form=>form.onsubmit=async event=>{event.preventDefault();const ids=[...form.querySelectorAll('input:checked')].map(input=>input.value);try{if(!ids.length)throw new Error('Selecione pelo menos uma fonte');await api('/api/imports/'+form.dataset.batch+'/confirm',{method:'POST',body:JSON.stringify({item_ids:ids})});await knowledgePanel(panel);}catch(error){errorMessage(error);}});
  panel.querySelectorAll('[data-remove-import]').forEach(button=>button.onclick=async()=>{if(!window.confirm('Remover este lote? Fontes sem outra importação serão excluídas. Execuções antigas mantêm seu registro.'))return;try{await api('/api/imports/'+button.dataset.removeImport,{method:'DELETE'});await knowledgePanel(panel);}catch(error){errorMessage(error);}});
  panel.querySelectorAll('[data-source-state]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await api('/api/documents/'+button.dataset.sourceState+'/state',{method:'PUT',body:JSON.stringify({active:button.dataset.active==='true'})});await knowledgePanel(panel);}catch(error){errorMessage(error);button.disabled=false;}});
  bindDocuments();
}

async function renderAISettings(){
  document.querySelector('#content').innerHTML=pageHead('MODELO E ORÇAMENTO','Configurar IA')+'<section class="card" id="ai-panel"></section>';
  await aiPanel(document.querySelector('#ai-panel'));
}

async function aiPanel(panel){
  const s=await api('/api/ai/config');if(!panel.isConnected)return;
  panel.innerHTML='<form id="ai-form" class="form"><label><span><input name="enabled" type="checkbox" style="width:auto" '+(s.enabled?'checked':'')+'> Ativar IA nesta instalação</span></label><label>Endereço base da API<input name="endpoint" type="url" value="'+esc(s.endpoint)+'" placeholder="https://provedor.example/v1"></label><label>Modelo<input name="model" value="'+esc(s.model)+'"></label><label>Chave própria<input name="api_key" type="password" autocomplete="new-password" placeholder="'+(s.has_key?'Já configurada; deixe vazio para manter no mesmo destino':'Informe sua chave')+'"></label><label>Chamadas por dia (UTC)<input name="daily_call_limit" type="number" min="1" max="1000" value="'+s.daily_call_limit+'" required></label><div class="grid grid-3"><label>Orçamento diário em US$ (opcional)<input name="daily_budget_usd" type="number" step="any" min="0.000001" max="1000" value="'+esc(s.daily_budget_usd)+'"></label><label>US$/milhão de tokens de entrada<input name="input_usd_per_million" type="number" step="any" min="0" max="1000" value="'+esc(s.input_usd_per_million)+'"></label><label>US$/milhão de tokens de saída<input name="output_usd_per_million" type="number" step="any" min="0" max="1000" value="'+esc(s.output_usd_per_million)+'"></label></div><p class="subtle">Preços são informados por você, na mesma moeda. Reserva estimada para até 32.768 tokens de entrada e 1.000 de saída; falhas sem uso conhecido mantêm a reserva. Isso não é confirmação de cobrança. Defina também limite no provedor. Chave salva somente nesta máquina em arquivo protegido, acessível ao administrador.</p><button class="btn primary" type="submit">Salvar configuração</button><p id="ai-saved" role="status"></p></form>';
  panel.querySelector('#ai-form').onsubmit=async event=>{event.preventDefault();const form=event.currentTarget;const values=Object.fromEntries(new FormData(form));values.enabled=form.elements.enabled.checked;values.daily_call_limit=Number(values.daily_call_limit);values.api_key=values.api_key||null;for(const key of ['daily_budget_usd','input_usd_per_million','output_usd_per_million'])values[key]=values[key]||null;try{await api('/api/ai/config',{method:'PUT',body:JSON.stringify(values)});form.elements.api_key.value='';panel.querySelector('#ai-saved').textContent='Configuração salva. Nenhuma chamada foi feita.';}catch(error){errorMessage(error);}};
}

function openTaskDialog() {
  const dialog = document.querySelector("#task-dialog");
  dialog.showModal();
  dialog.querySelector("input[name=title]").focus();
}

async function submitTask(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  values.priority = Number(values.priority);
  if (!values.area_id) values.area_id = null;
  if (!values.due_date) values.due_date = null;
  try {
    await api("/api/tasks", { method: "POST", body: JSON.stringify(values) });
    form.reset();
    document.querySelector("#task-dialog").close();
    await refresh();
    navigate("today");
    showToast("Tarefa criada");
  } catch (error) { errorMessage(error); }
}

async function submitArea(event) {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await api("/api/areas", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form))) });
    form.reset();
    document.querySelector("#area-dialog").close();
    await refresh();
    renderShell();
    navigate("areas");
    showToast("Área criada");
  } catch (error) { errorMessage(error); }
}

boot();

