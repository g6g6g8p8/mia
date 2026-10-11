const app = document.querySelector("#app");
const toast = document.querySelector("#toast");
let state = { view: "today", owner: null, areas: [], today: null };

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
    pageHead("SEUS CONTEXTOS", "Áreas", '<button class="btn primary" data-open-area>+ Área</button>') +
    '<p class="lede">Cada área delimita um contexto. A instalação começou vazia e mostra somente o que você criou.</p>' +
    '<section class="section grid grid-3">' + state.areas.map(areaCard).join("") + '</section>';
  document.querySelector("[data-open-area]").addEventListener("click", function () {
    document.querySelector("#area-dialog").showModal();
  });
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
          return '<article class="result"><span class="badge">' + esc(result.type === "task" ? "tarefa" : "área") + '</span>' +
            '<h3 style="margin-top:10px">' + esc(result.title) + '</h3><p class="subtle">' + esc(result.notes || "") + '</p>' +
            '<div class="task-meta">' + esc(result.area_name || "") + (result.due_date ? " · " + localDate(result.due_date) : "") + '</div></article>';
        }).join("") : '<div class="empty">Nenhum resultado.</div>';
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
    '<article class="card"><p class="kicker">STATUS</p><h2>Protótipo M2</h2><p class="subtle">Contexto por área e tarefas propostas com confirmação. Sem conectores externos ou conversa contínua ainda.</p></article></section>';
}

async function renderIntelligence() {
  const [settings, runs] = await Promise.all([api("/api/ai/config"), api("/api/runs")]);
  if (state.view !== "intelligence") return;
  const labels = {running:"Em andamento",awaiting_confirmation:"Aguardando confirmação",completed:"Concluída",failed:"Falhou",rejected:"Recusada"};
  document.querySelector("#content").innerHTML = pageHead("CONTEXTO E AÇÃO", "Inteligência") +
    '<section class="card"><p class="lede">' + (settings.enabled ? esc(settings.model) + ' · ' + esc(settings.endpoint) : 'IA desativada. Configure o provedor, o modelo e a chave no .env desta instalação.') + '</p>' +
    '<p class="subtle">Uma chamada por pedido; até ' + settings.daily_call_limit + ' chamadas/dia (UTC), 1.000 tokens de saída e 45 segundos. Preço não configurado: custo monetário desconhecido. Defina também um limite no provedor.</p>' +
    '<form class="form" id="run-form"><label>Área autorizada<select name="area_id">' + state.areas.map(a=>'<option value="'+esc(a.id)+'">'+esc(a.name)+'</option>').join('') + '</select></label>' +
    '<button type="button" class="btn" id="preview-context">Ver contexto que será enviado</button><pre id="context-preview" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre>' +
    '<label>Seu pedido<textarea name="message" required minlength="2" maxlength="4000" placeholder="O que merece atenção nesta área? Ou: proponha uma tarefa para amanhã."></textarea></label>' +
    '<label><input type="checkbox" name="consent" required style="width:auto"> Autorizo enviar este pedido e o contexto da área ao provedor mostrado acima.</label>' +
    '<p class="subtle">Até 12 tarefas recentes da área, com notas limitadas a 500 caracteres. Não envia outras áreas, e-mail ou senhas. Cada pedido é independente, sem histórico de conversa automático.</p>' +
    '<button class="btn primary" type="submit" '+(!settings.enabled?'disabled':'')+'>Enviar pedido</button></form></section>' +
    '<section class="section"><h2>Execuções recentes</h2>' + runs.map(r=>{
      const p=r.proposal;
      return '<article class="card section"><span class="badge">'+esc(labels[r.state]||r.state)+'</span><h3>'+esc(r.request.message)+'</h3>' +
        '<p style="white-space:pre-wrap">'+esc(r.answer||r.error||'Aguardando resposta. Atualize esta aba em alguns instantes.')+'</p>' +
        (p?'<div class="card"><h3>Proposta: '+esc(p.title)+'</h3><p>'+esc(p.notes)+'</p><p>Data: '+esc(p.due_date||'sem data')+' · Prioridade: '+p.priority+'</p>'+
        (r.state==='awaiting_confirmation'?'<button class="btn primary" data-decision="approve" data-run="'+esc(r.id)+'">Confirmar e criar tarefa</button> <button class="btn" data-decision="reject" data-run="'+esc(r.id)+'">Recusar</button>':'')+'</div>':'') +
        '<details><summary>Contexto enviado · '+r.sources.length+' fontes (não é verificação automática da resposta)</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(JSON.stringify(r.sources,null,2))+'</pre></details>' +
        '<p class="subtle">Tokens informados pelo provedor: '+esc(r.usage?.total_tokens??'não informado')+' · Custo: desconhecido</p></article>';
    }).join('')+'</section>';
  const form=document.querySelector('#run-form');
  document.querySelector('#preview-context').onclick=async()=>{
    try { const data=await api('/api/ai/context?area_id='+encodeURIComponent(form.elements.area_id.value));
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

