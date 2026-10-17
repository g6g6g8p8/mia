import {renderPersonalizationPage} from './personalization.js';
import {guideAI} from './ai-setup.js';
import {renderAccess} from './access.js';
import {renderBackups} from './backups.js';
import {renderOperations} from './operations.js';
import {migrationPanel} from './migration.js';
import {renderOnboarding} from './onboarding.js';
import {renderTodayExperience,locationCard,focusPanel} from './today.js';
import {renderConversations} from './conversations.js';

const app = document.querySelector("#app");
const toast = document.querySelector("#toast");
const clientParameters = new URLSearchParams(window.location.search);
// These parameters select presentation only. The backend still authenticates
// every operation and declares the destination before a file can be imported.
const desktop = clientParameters.get('mia_client') === 'mac' && ['local','remote'].includes(clientParameters.get('mia_mode'))
  ? Object.freeze({mode:clientParameters.get('mia_mode')}) : null;
if (desktop) document.body.classList.add('desktop-client');
let state = { view: "today", owner: null, areas: [], today: null, onboarding: null, installation: null };

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

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && options.body != null) {
    headers.set('Content-Type', options.body instanceof Blob ? 'application/octet-stream' : 'application/json');
  }
  const response = await fetch(path, {...options, credentials:'same-origin', headers});
  if (response.status === 401) {
    renderLogin();
    throw new Error("Entre para continuar");
  }
  const isJson = (response.headers.get('content-type') || '').includes('json');
  const data = isJson ? await response.json() : null;
  if (!response.ok) {
    const detail=data?.detail;
    const message=Array.isArray(detail) ? detail.map(item=>item.msg).join('; ') : typeof detail==='string' ? detail : detail ? JSON.stringify(detail) : 'Não foi possível concluir';
    const error=new Error(message);error.status=response.status;throw error;
  }
  if (path === '/api/installation' || path === '/api/location' || path === '/api/experience') {
    state.installation = data?.location || data;
    updateDesktopDestination();
  }
  return data;
}

function context(){return {state,desktop,api,esc,pageHead,errorMessage,navigate,refresh,bindDocuments,aiPanel,taskCard,bindTaskActions,openTaskDialog};}

function desktopDestination() {
  return {local:'Dados neste computador',remote:'Dados no seu servidor',unknown:'Destino a confirmar'}[state.installation?.mode] || 'Destino a confirmar';
}

function desktopHeader() {
  return desktop ? '<header class="desktop-context" aria-label="Sua instalação"><span class="desktop-product">Mia <span class="badge">Demo</span></span><span id="desktop-destination">'+esc(desktopDestination())+'</span></header>' : '';
}

function updateDesktopDestination() {
  const label=document.querySelector('#desktop-destination');
  if (label) label.textContent=desktopDestination();
}

function errorMessage(error) {
  showToast(error instanceof Error ? error.message : "Não foi possível concluir");
}

async function boot() {
  try {
    if (desktop) await api('/api/installation');
    const status = await api("/api/status");
    if (!status.configured) {
      await renderSetup();
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

async function renderSetup() {
  const installation=await api("/api/installation");
  app.innerHTML =
    desktopHeader()+'<main class="auth"><section class="card auth-card">' +
    '<img src="/assets/mia-icon.svg" class="auth-logo" alt="Gatinha da Mia">' +
    '<p class="kicker">'+(desktop?'ESTA MIA É SUA':'PRIMEIRO ACESSO')+'</p><h1>Seu contexto, reunido na Mia.</h1>' +
    '<p class="lede">Retome projetos, encontre decisões e avance com fontes. Crie seu acesso nesta instalação; depois traga seu contexto. Nenhuma conta externa é necessária.</p>' +
    locationCard(installation.location || installation,esc,true) +
    '<form id="setup-form" class="form">' +
    '<div class="grid grid-2"><label>Seu nome<input name="name" required minlength="2" autocomplete="name"></label>' +
    '<label>E-mail opcional<input name="email" type="email" autocomplete="email"></label></div>' +
    '<label>Fuso horário<input name="timezone" value="' + esc(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC") + '" required></label>' +
    '<label>Senha de acesso à Mia<input name="password" type="password" required minlength="10" autocomplete="new-password"><span class="subtle">Use pelo menos 10 caracteres.</span></label>' +
    '<p class="subtle">'+(desktop?'Sua biblioteca começa vazia. Você escolhe o que trazer; seus arquivos originais permanecem intactos.':'O código da Mia é distribuído pelo GitHub. Seus dados ficam nesta instalação; importar não os envia à IA.')+'</p>' +
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
  document.querySelectorAll("dialog").forEach(dialog=>dialog.remove());
  app.innerHTML =
    desktopHeader()+'<main class="auth"><section class="card auth-card">' +
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
    desktopHeader()+'<div class="shell"><aside class="sidebar"><div class="brand">' +
    '<img src="/assets/mia-icon.svg" alt=""><div><div class="brand-name">Mia</div><div class="brand-tag">seu contexto de trabalho</div></div></div>' +
    '<nav class="nav" aria-label="Principal"><button data-view="today">Hoje</button><button data-view="conversations">Conversas</button><button data-view="library">Biblioteca</button><button data-view="settings">Ajustes</button></nav><button class="btn ghost sidebar-search" id="global-search">Buscar nas fontes</button>' +
    '<div class="sidebar-foot"><span class="subtle">' + esc(state.owner.name) + '</span><button class="btn ghost" id="logout">Sair</button></div>' +
    '</aside><main class="content" id="content"></main></div>' + dialogs();
  document.querySelectorAll("[data-view]").forEach(function (button) {
    button.addEventListener("click", function () { navigate(button.dataset.view); });
  });
  document.querySelector("#global-search").onclick=()=>navigate("search");
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

function navigate(view, selectedId=null, initialMessage='') {
  view=({knowledge:'library',system:'settings',intelligence:'conversations'})[view] || view;
  state.view = view;
  const section=['areas','organization','personalization','search'].includes(view)?'library':['access','backups','operations','ai-settings','request-history'].includes(view)?'settings':view;
  document.querySelectorAll('[data-view]').forEach(button=>button.classList.toggle('active',button.dataset.view===section));
  const routes={today:()=>renderTodayExperience(context()),conversations:()=>renderConversations(context(),selectedId,initialMessage),library:renderLibrary,settings:renderSystem,areas:renderAreas,search:renderSearch,
    access:()=>renderAccess({api,esc,pageHead,errorMessage}),backups:()=>renderBackups({api,esc,pageHead,errorMessage}),operations:()=>renderOperations({api,esc,pageHead,errorMessage}),
    onboarding:()=>renderOnboarding(context()),'ai-settings':renderAISettings,organization:renderOrganization,personalization:renderPersonalization,'request-history':renderIntelligence};
  const content=document.querySelector('#content');
  if(content)content.innerHTML='<p class="subtle" role="status">Abrindo…</p>';
  Promise.resolve().then(()=>routes[view]?.()).catch(error=>{errorMessage(error);if(state.view===view && content?.isConnected)content.innerHTML='<section class="card"><h2>Não foi possível abrir esta tela.</h2><p>'+esc(error.message)+'</p><button class="btn" id="retry-view">Tentar novamente</button></section>';content?.querySelector('#retry-view')?.addEventListener('click',()=>navigate(view,selectedId,initialMessage));});
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
    area.open_tasks + " tarefa" + (area.open_tasks == 1 ? "" : "s") + " aberta" + (area.open_tasks == 1 ? "" : "s") + '</div><button class="btn" data-edit-area="'+esc(area.id)+'">Editar área</button></article>';
}

function openAreaEditor(id){
  const area=state.areas.find(a=>a.id===id);
  const dialog=document.querySelector('#area-dialog'),form=dialog.querySelector('form');
  form.reset();form.dataset.areaId=id||'';
  dialog.querySelector('h2').textContent=area?'Editar área':'Criar área';
  dialog.querySelector('.kicker').textContent=area?'SEU CONTEXTO':'NOVO CONTEXTO';
  form.querySelector('[type=submit]').textContent=area?'Salvar área':'Criar área';
  if(area)for(const key of ['name','description','color'])form.elements[key].value=area[key];
  dialog.showModal();
}

function bindAreaActions(){document.querySelectorAll('[data-edit-area]').forEach(button=>button.onclick=()=>openAreaEditor(button.dataset.editArea));}


function renderAreas() {
  document.querySelector("#content").innerHTML =
    pageHead("SEUS CONTEXTOS", "Áreas", '<div><button class="btn" id="open-knowledge">Fontes</button> <button class="btn primary" data-open-area>+ Área</button></div>') +
    '<p class="lede">Cada área delimita um contexto. A instalação começou vazia e mostra somente o que você criou.</p>' +
    '<section class="section grid grid-3">' + state.areas.map(areaCard).join("") + '</section>';
  document.querySelector("[data-open-area]").addEventListener("click", function () {
    openAreaEditor();
  });
  document.querySelector('#open-knowledge').onclick=()=>navigate('knowledge');
  bindAreaActions();
}

function renderSearch() {
  document.querySelector("#content").innerHTML =
    pageHead("EVIDÊNCIA LOCAL", "Busca") +
    '<input class="search" id="search-input" placeholder="Encontre uma decisão, projeto ou informação…" autofocus>' +
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

async function renderSystem() {
  const experience=await api('/api/experience');if(state.view!=='settings')return;
  const maintenance=desktop
    ? '<article class="card"><p class="kicker">CONTINUIDADE</p><h2>Minha instalação</h2><p class="subtle">No menu Mia, abra Minha instalação para conexão, cópia de recuperação e atualização.</p><div class="actions"><button class="btn" id="resume-guide">Retomar preparação</button><button class="btn ghost" id="system-history">Histórico de pedidos</button></div></article>'
    : '<article class="card"><p class="kicker">CONTINUIDADE</p><h2>Preparação e manutenção</h2><p class="subtle">Reveja sua migração, o serviço que mantém a Mia disponível e as instruções de atualização.</p><div class="actions"><button class="btn" id="resume-guide">Retomar preparação</button><button class="btn" id="system-operations">Serviço e atualização</button><button class="btn ghost" id="system-history">Histórico de pedidos</button></div></article>';
  document.querySelector('#content').innerHTML=pageHead('ESCOLHAS E CONTROLE','Ajustes')+
    locationCard(experience.location,esc,!!desktop)+
    '<section class="grid grid-2 section"><article class="card"><p class="kicker">SEU ACESSO</p><h2>'+esc(state.owner.name)+'</h2><p class="subtle">'+esc(state.owner.email || 'Sem e-mail')+' · '+esc(state.owner.timezone)+'</p><button class="btn" id="system-access">Acesso e disponibilidade</button></article>'+
    '<article class="card"><p class="kicker">IA E CUSTOS</p><h2>Modelo opcional</h2><p class="subtle">Importe e busque sem IA. Escolha o destino, a autorização e os limites antes de fazer um pedido.</p><button class="btn" id="system-ai">Configurar IA e limites</button></article>'+
    '<article class="card"><p class="kicker">SEUS DADOS</p><h2>Backup e portabilidade</h2><p class="subtle">Exporte seu contexto ou prepare uma cópia de recuperação desta instalação.</p><div class="actions"><a class="btn" href="/api/export">Exportar dados</a><button class="btn" id="system-backups">Backups</button></div></article>'+
    maintenance+'</section>'+
    (!desktop || experience.location?.mode==='unknown'?'<section class="card section"><h3>Registrar onde esta Mia está instalada</h3><p class="subtle">Esta informação descreve o destino dos arquivos. Não instala serviços, move dados ou abre acesso remoto.</p><form class="form" id="settings-location"><label>Destino<select name="mode"><option value="local" '+(experience.location?.mode==='local'?'selected':'')+'>Neste computador</option><option value="remote" '+(experience.location?.mode==='remote'?'selected':'')+'>No meu servidor</option></select></label><button class="btn" type="submit">Confirmar destino</button></form></section>':'');
  const links={'#system-access':'access','#system-ai':'ai-settings','#system-backups':'backups','#resume-guide':'onboarding','#system-operations':'operations','#system-history':'request-history'};
  Object.entries(links).forEach(([selector,view])=>document.querySelector(selector)?.addEventListener('click',()=>navigate(view)));
  document.querySelector('#settings-location')?.addEventListener('submit',async event=>{event.preventDefault();try{await api('/api/location',{method:'PUT',body:JSON.stringify({mode:event.currentTarget.elements.mode.value})});await renderSystem();}catch(error){errorMessage(error);}});
}

async function renderIntelligence() {
  const [settings, runs] = await Promise.all([api("/api/ai/config"), api("/api/runs")]);
  if (state.view !== "request-history") return;
  const labels = {running:"Em andamento",awaiting_confirmation:"Aguardando confirmação",completed:"Concluída",failed:"Falhou",rejected:"Recusada"};
  document.querySelector("#content").innerHTML = pageHead("PEDIDOS ANTERIORES", "Histórico de pedidos") +
    '<section class="card"><p class="lede">' + (settings.enabled ? esc(settings.model) + ' · ' + esc(settings.endpoint) : 'IA desativada. Configure seu modelo em Ajustes ou continue usando a busca.') + '</p>' +
    '<p class="subtle">Até ' + settings.daily_call_limit + ' chamadas/dia (UTC), 1.000 tokens de saída e 45 segundos. '+(settings.daily_budget_usd?'Orçamento estimado: US$ '+esc(settings.daily_budget_usd)+'/dia.':'Custo desconhecido; nenhum orçamento monetário configurado.')+' Defina também um limite no provedor.</p>' +
    '<form class="form" id="run-form"><label>Área autorizada<select name="area_id">' + state.areas.map(a=>'<option value="'+esc(a.id)+'">'+esc(a.name)+'</option>').join('') + '</select></label>' +
    '<label><span><input type="checkbox" name="include_personal_context" style="width:auto"> Incluir meu contexto pessoal e objetivo confirmados nesta consulta</span></label>'+
    '<button type="button" class="btn" id="preview-context">Ver contexto que será enviado</button><pre id="context-preview" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre>' +
    '<label>Seu pedido<textarea name="message" required minlength="2" maxlength="4000" placeholder="O que merece atenção nesta área? Ou: proponha uma tarefa para amanhã."></textarea></label>' +
    '<label><input type="checkbox" name="consent" required style="width:auto"> Autorizo enviar este pedido e o contexto da área ao provedor mostrado acima.</label>' +
    '<p class="subtle">Até 12 tarefas e 3 trechos de fontes da área encontrados pelo seu pedido. Contexto pessoal e objetivo só são incluídos se marcados acima; confira a prévia. Pedidos independentes.</p>' +
    '<button class="btn primary" type="submit" '+(!settings.enabled?'disabled':'')+'>Enviar pedido</button></form></section>' +
    '<section class="section"><h2>Execuções recentes</h2>' + runs.map(r=>{
      if(r.request.purpose==='organization')return '<article class="card section"><span class="badge">'+esc(labels[r.state]||r.state)+'</span><h3>Organização da Biblioteca</h3><p>'+esc(r.error||r.answer||'Proposta de áreas com fontes selecionadas.')+'</p><button class="btn" data-open-organization>Revisar organização</button></article>';
      if(r.request.purpose==='personalization')return '<article class="card section"><span class="badge">'+esc(labels[r.state]||r.state)+'</span><h3>Contexto e objetivo</h3><p>'+esc(r.error||r.answer||'Sugestões para revisão.')+'</p><button class="btn" data-open-personalization>Revisar personalização</button></article>';
      const p=r.proposal;
      return '<article class="card section"><span class="badge">'+esc(labels[r.state]||r.state)+'</span><h3>'+esc(r.request.message)+'</h3>' +
        '<p style="white-space:pre-wrap">'+esc(r.answer||r.error||'Aguardando resposta. Atualize esta aba em alguns instantes.')+'</p>' +
        (p?'<div class="card"><h3>Proposta: '+esc(p.title)+'</h3><p>'+esc(p.notes)+'</p><p>Data: '+esc(p.due_date||'sem data')+' · Prioridade: '+p.priority+'</p>'+
        (r.state==='awaiting_confirmation'?'<form class="form" data-task-review="'+esc(r.id)+'"><label>Título da tarefa<input name="title" required minlength="2" maxlength="200" value="'+esc(p.title)+'"></label><label>Notas da tarefa<textarea name="notes" maxlength="10000">'+esc(p.notes)+'</textarea></label><label>Data da tarefa<input name="due_date" type="date" value="'+esc(p.due_date||'')+'"></label><label>Prioridade da tarefa<input name="priority" type="number" min="1" max="3" required value="'+p.priority+'"></label><p class="subtle">Revise antes de confirmar. A área autorizada permanece a mesma.</p><button class="btn primary" type="submit">Confirmar e criar tarefa</button> <button type="button" class="btn" data-decision="reject" data-run="'+esc(r.id)+'">Recusar</button></form>':'')+
        (r.task_result?'<p>Tarefa aplicada: '+esc(r.task_result.title)+' · Data: '+esc(r.task_result.due_date||'sem data')+' · Prioridade: '+r.task_result.priority+'</p>':'')+'</div>':'') +
        '<details><summary>Contexto enviado · '+r.sources.length+' fontes (não é verificação automática da resposta)</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(JSON.stringify(r.sources,null,2))+'</pre></details>' +
        '<p class="subtle">Tokens: '+esc(r.usage?.total_tokens??'não informado')+' · '+(r.estimated_cost_usd!==null?'Custo estimado US$ '+r.estimated_cost_usd:r.cost_status==='unknown'?'Custo desconhecido':r.cost_status==='overrun'?'Uso excedeu os limites; novas chamadas bloqueadas':'Custo não confirmado; reserva US$ '+r.reserved_usd)+'</p>'+
        (r.invalid_citations.length?'<p class="subtle">Referências não reconhecidas: '+esc(r.invalid_citations.join(', '))+'</p>':'')+
        r.sources.filter(s=>s.source.startsWith('doc:')).map(s=>'<button class="btn" data-document="'+esc(s.id)+'">Abrir '+esc(s.title)+'</button>').join('')+'</article>';
    }).join('')+'</section>';
  const form=document.querySelector('#run-form');
  document.querySelector('#preview-context').onclick=async()=>{
    try { const data=await api('/api/ai/context?area_id='+encodeURIComponent(form.elements.area_id.value)+'&q='+encodeURIComponent(form.elements.message.value)+'&include_personal_context='+form.elements.include_personal_context.checked);
      const preview=document.querySelector('#context-preview'); if(preview) preview.textContent=JSON.stringify(data,null,2);
    } catch(error){errorMessage(error);}
  };
  form.onsubmit=async event=>{
    event.preventDefault();
    const button=form.querySelector('[type=submit]'); button.disabled=true; button.textContent='Processando…';
    const values={message:form.elements.message.value,area_id:form.elements.area_id.value,consent:form.elements.consent.checked,include_personal_context:form.elements.include_personal_context.checked,request_key:crypto.randomUUID()};
    try { await api('/api/runs',{method:'POST',body:JSON.stringify(values)}); await renderIntelligence(); }
    catch(error){errorMessage(error); button.disabled=false; button.textContent='Enviar pedido';}
  };
  document.querySelectorAll('[data-decision]').forEach(button=>button.onclick=async()=>{
    button.disabled=true;
    try { await api('/api/runs/'+button.dataset.run+'/'+button.dataset.decision,{method:'POST',body:'{}'}); await refresh(); await renderIntelligence(); }
    catch(error){errorMessage(error);button.disabled=false;}
  });
  document.querySelectorAll('[data-task-review]').forEach(review=>review.onsubmit=async event=>{
    event.preventDefault();const button=review.querySelector('[type=submit]');button.disabled=true;
    const edits=Object.fromEntries(new FormData(review));edits.priority=Number(edits.priority);edits.due_date=edits.due_date||null;
    try{await api('/api/runs/'+review.dataset.taskReview+'/approve',{method:'POST',body:JSON.stringify({edits})});await refresh();await renderIntelligence();}
    catch(error){errorMessage(error);button.disabled=false;}
  });
  bindDocuments();
  document.querySelectorAll('[data-open-organization]').forEach(button=>button.onclick=()=>navigate('organization'));
  document.querySelectorAll('[data-open-personalization]').forEach(button=>button.onclick=()=>navigate('personalization'));
}

function bindDocuments(){
  document.querySelectorAll('[data-document]').forEach(button=>button.onclick=async()=>{
    try {
      const doc=await api('/api/documents/'+button.dataset.document);
      const prior=document.querySelector('#source-dialog'); if(prior) prior.remove();
      const dialog=document.createElement('dialog'); dialog.id='source-dialog';dialog.className='dialog';
      dialog.innerHTML='<div class="dialog-body"><h2>'+esc(doc.title)+'</h2><p class="subtle">'+esc(doc.kind)+' · '+esc(doc.path)+' · Importado em '+esc(doc.created_at)+' · '+(doc.active?'Ativa':'Pausada — fora de novas consultas')+'</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(doc.content)+'</pre><button class="btn" id="close-source">Fechar fonte</button></div>';
      document.body.append(dialog); dialog.onclose=()=>dialog.remove();dialog.showModal(); dialog.querySelector('#close-source').onclick=()=>dialog.close();
    }catch(error){errorMessage(error);}
  });
}

async function renderLibrary(){
  const [experience,docs,legacy]=await Promise.all([api('/api/experience'),api('/api/documents'),api('/api/imports')]);
  if(state.view!=='library')return;
  document.querySelector('#content').innerHTML=pageHead('SEU CONTEXTO E SUAS ORIGENS','Biblioteca','<button class="btn" id="library-search">Buscar</button>')+
    '<p class="lede">O material que você autorizou a Mia a consultar. Fontes, organização e informações sobre você são coisas diferentes.</p><div class="actions"><button class="btn" id="organize-sources">Organizar fontes</button><button class="btn" id="library-areas">Projetos e áreas</button><button class="btn" id="library-profile">Sobre mim</button></div>'+
    '<section class="card section" id="migration-panel"></section>'+
    '<section class="section"><div class="section-head"><h2 id="library-source-count">Fontes ('+Number(experience.library?.active || 0)+' ativas)</h2></div><p class="subtle">Pausar tira uma fonte da busca e dos novos pedidos. A fonte permanece guardada/exportável e o histórico antigo preserva seu registro.</p><label>Filtrar títulos e caminhos<input type="search" id="library-filter" placeholder="Projeto, pasta ou título"></label><div class="list section" id="library-documents"></div><div class="actions section" id="library-pagination"></div></section>'+
    (legacy.length?'<details class="section"><summary>Importações da experiência anterior ('+legacy.length+')</summary><div class="list" id="legacy-imports"></div></details>':'');
  document.querySelector('#library-search').onclick=()=>navigate('search');document.querySelector('#organize-sources').onclick=()=>navigate('organization');document.querySelector('#library-areas').onclick=()=>navigate('areas');document.querySelector('#library-profile').onclick=()=>navigate('personalization');
  let page=0,query='';
  function sources(){
    if(state.view!=='library')return;
    document.querySelector('#library-source-count').textContent='Fontes ('+docs.filter(doc=>doc.active).length+' ativas)';
    const filtered=docs.filter(doc=>(doc.title+' '+doc.path).toLocaleLowerCase().includes(query.toLocaleLowerCase()));const start=page*20;
    document.querySelector('#library-documents').innerHTML=filtered.slice(start,start+20).map(doc=>'<article class="card source-row"><div><h3>'+esc(doc.title)+'</h3><p class="subtle">'+esc(doc.path)+' · '+esc(doc.kind)+' · '+(doc.active?'Ativa':'Pausada')+'</p><p class="subtle">Importação: '+esc(doc.created_at)+'. Esta data não confirma que o conteúdo continua atual.</p></div><div class="actions"><button class="btn" data-document="'+esc(doc.id)+'">Abrir fonte</button><button class="btn ghost" data-source-state="'+esc(doc.id)+'">'+(doc.active?'Pausar':'Reativar')+'</button></div></article>').join('') || '<p class="subtle">Nenhuma fonte neste filtro.</p>';
    document.querySelector('#library-pagination').innerHTML='<button class="btn" id="sources-prev" '+(page===0?'disabled':'')+'>Anteriores</button><span class="subtle">'+filtered.length+' fontes · página '+(page+1)+'</span><button class="btn" id="sources-next" '+(start+20>=filtered.length?'disabled':'')+'>Próximas</button>';
    document.querySelector('#sources-prev').onclick=()=>{page--;sources();};document.querySelector('#sources-next').onclick=()=>{page++;sources();};
    document.querySelectorAll('[data-source-state]').forEach(button=>button.onclick=async()=>{const doc=docs.find(d=>d.id===button.dataset.sourceState);button.disabled=true;try{await api('/api/documents/'+doc.id+'/state',{method:'PUT',body:JSON.stringify({active:!doc.active})});doc.active=!doc.active;sources();}catch(error){errorMessage(error);button.disabled=false;}});bindDocuments();
  }
  sources();document.querySelector('#library-filter').oninput=event=>{query=event.target.value;page=0;sources();};
  const legacyPanel=document.querySelector('#legacy-imports');
  if(legacyPanel){legacyPanel.innerHTML=legacy.map(batch=>'<article class="card"><h3>'+esc(batch.name)+'</h3><p class="subtle">'+(batch.state==='review'?'Aguardando revisão':'Concluída')+'</p>'+(batch.state==='review'?'<form data-legacy-batch="'+esc(batch.id)+'">'+batch.items.map(item=>'<label class="check-label"><input type="checkbox" name="item" value="'+esc(item.id)+'">'+esc(item.title)+'</label>').join('')+'<button type="submit" class="btn">Autorizar selecionados</button></form>':'')+'<details><summary>Relatório</summary><pre class="source-preview">'+esc(JSON.stringify(batch.report,null,2))+'</pre></details><button class="btn ghost" data-remove-import="'+esc(batch.id)+'">Excluir lote</button></article>').join('');legacyPanel.querySelectorAll('[data-legacy-batch]').forEach(form=>form.onsubmit=async event=>{event.preventDefault();try{const item_ids=[...form.querySelectorAll('[name=item]:checked')].map(input=>input.value);if(!item_ids.length)throw new Error('Selecione uma fonte');await api('/api/imports/'+form.dataset.legacyBatch+'/confirm',{method:'POST',body:JSON.stringify({item_ids})});await renderLibrary();}catch(error){errorMessage(error);}});legacyPanel.querySelectorAll('[data-remove-import]').forEach(button=>button.onclick=async()=>{if(!window.confirm('Excluir este lote? Fontes sem outra origem serão removidas; o histórico anterior permanece.'))return;try{await api('/api/imports/'+button.dataset.removeImport,{method:'DELETE'});await renderLibrary();}catch(error){errorMessage(error);}});}
  await migrationPanel(document.querySelector('#migration-panel'),{...context(),location:experience.location});
}

async function renderAISettings(){
  document.querySelector('#content').innerHTML=pageHead('ESCOLHA OPCIONAL','IA e limites')+'<section class="card" id="ai-panel"></section>';
  await aiPanel(document.querySelector('#ai-panel'));
}

async function renderOrganization(selectedArea){
  const [settings,docs,allRuns]=await Promise.all([api('/api/ai/config'),api('/api/documents'),api('/api/runs')]);
  if(state.view!=='organization')return;
  const areaId=selectedArea||state.areas[0]?.id;
  const available=docs.filter(d=>d.active&&d.area_id===areaId);
  const runs=allRuns.filter(r=>r.request.purpose==='organization');
  const labels={running:'Em andamento',awaiting_confirmation:'Aguardando revisão',completed:'Concluída',failed:'Falhou',rejected:'Recusada'};
  document.querySelector('#content').innerHTML=pageHead('PERSONALIZAR SUA MIA','Organizar minhas fontes')+
    '<section class="card"><p class="lede">Escolha até seis fontes da mesma área. A Mia sugere novas áreas e descrições; você edita e decide o que aplicar.</p><p class="subtle">'+(settings.enabled?esc(settings.model)+' · '+esc(settings.endpoint):'Configure sua IA em Ajustes para gerar sugestões.')+' Até '+settings.daily_call_limit+' chamadas/dia (UTC). '+(settings.daily_budget_usd?'Orçamento estimado: US$ '+esc(settings.daily_budget_usd)+'/dia.':'Custo desconhecido; nenhum orçamento monetário configurado.')+'</p>'+
    '<form class="form" id="organization-form"><label>Área das fontes<select name="area_id">'+state.areas.map(a=>'<option value="'+esc(a.id)+'" '+(a.id===areaId?'selected':'')+'>'+esc(a.name)+'</option>').join('')+'</select></label>'+
    (available.length?available.map(d=>'<label><span><input type="checkbox" name="source" value="'+esc(d.id)+'" style="width:auto"> '+esc(d.title)+' · '+esc(d.path)+'</span></label>').join(''):'<p>Nenhuma fonte ativa nesta área. Importe notas em Fontes para começar.</p>')+
    '<label>Como gostaria de organizar? (opcional)<textarea name="message" maxlength="4000" placeholder="Ex.: separar trabalho e estudos."></textarea></label><button class="btn" type="button" id="organization-preview">Ver trechos que serão enviados</button><pre id="organization-context" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre>'+
    '<p class="subtle">Somente o início das fontes selecionadas: até 1.800 bytes de texto por fonte. A proposta pode ser incompleta. Conversas antigas não comprovam prioridades atuais. Gerar usa uma chamada com os mesmos limites dos pedidos de IA.</p>'+
    '<label><span><input type="checkbox" name="consent" required style="width:auto"> Autorizo enviar os trechos selecionados e meu pedido ao provedor acima.</span></label><button type="submit" class="btn primary" '+(!settings.enabled||!available.length?'disabled':'')+'>Gerar sugestões de áreas</button></form></section>'+
    '<section class="section"><h2>Suas propostas de organização</h2><p class="subtle">Confirmar cria novas áreas e move as fontes selecionadas para elas, preservando conteúdo e origem. Fontes desmarcadas ficam onde estão. Tarefas e objetivo pessoal não são alterados. Edições são salvas ao confirmar.</p><p class="subtle">Descrições aprovadas passam a ser contexto das áreas, mesmo se as fontes forem pausadas ou excluídas depois. Você pode alterá-las em Biblioteca → Projetos e áreas → Editar área.</p>'+runs.map(r=>{
      const p=r.proposal;
      return '<article class="card section"><span class="badge">'+esc(labels[r.state]||r.state)+'</span><p style="white-space:pre-wrap">'+esc(r.answer||r.error||'Atualize em alguns instantes.')+'</p>'+
        (p&&r.state==='awaiting_confirmation'?'<form class="form" data-organization-run="'+esc(r.id)+'">'+p.areas.map((a,i)=>'<fieldset data-group="'+i+'"><legend><label><span><input type="checkbox" name="include" style="width:auto"> Aplicar esta área</span></label></legend><label>Nome da área sugerida<input name="area_name" value="'+esc(a.name)+'" minlength="2" maxlength="80" required></label><label>Descrição sugerida<textarea name="description" maxlength="500">'+esc(a.description)+'</textarea></label>'+a.document_ids.map(id=>'<label><span><input type="checkbox" name="document" value="'+esc(id)+'" checked style="width:auto"> '+esc(r.sources.find(s=>s.id===id)?.title||id)+'</span></label><button type="button" class="btn" data-document="'+esc(id)+'">Conferir fonte</button>').join('')+'</fieldset>').join('')+'<button class="btn primary" type="submit">Confirmar organização selecionada</button><button class="btn" type="button" data-reject-organization="'+esc(r.id)+'">Recusar organização</button></form>':'')+
        (r.organization_result?'<p>Áreas criadas: '+r.organization_result.created_areas.map(a=>esc(a.name)).join(', ')+'.</p>':'')+
        '<details><summary>Trechos usados nesta proposta</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(JSON.stringify(r.sources,null,2))+'</pre></details><p class="subtle">'+(r.estimated_cost_usd!==null?'Custo estimado US$ '+r.estimated_cost_usd:r.cost_status==='unknown'?'Custo desconhecido':r.cost_status==='overrun'?'Uso excedeu limites; novas chamadas bloqueadas':'Custo não confirmado; reserva US$ '+r.reserved_usd)+'</p></article>';
    }).join('')+'</section>';
  const form=document.querySelector('#organization-form');
  form.elements.area_id.onchange=()=>renderOrganization(form.elements.area_id.value).catch(errorMessage);
  const selection=()=>({area_id:form.elements.area_id.value,document_ids:[...form.querySelectorAll('[name=source]:checked')].map(input=>input.value)});
  form.querySelector('#organization-preview').onclick=async()=>{try{const data=await api('/api/organization/preview',{method:'POST',body:JSON.stringify(selection())});if(form.isConnected)form.querySelector('#organization-context').textContent=JSON.stringify(data,null,2);}catch(error){errorMessage(error);}};
  let requestKey=crypto.randomUUID(),previousRequest='';
  form.onsubmit=async event=>{
    event.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;
    const values={...selection(),purpose:'organization',message:form.elements.message.value.trim()||'Sugira áreas para organizar as fontes selecionadas.',consent:form.elements.consent.checked};
    const fingerprint=JSON.stringify(values);if(previousRequest&&previousRequest!==fingerprint)requestKey=crypto.randomUUID();previousRequest=fingerprint;
    try{await api('/api/runs',{method:'POST',body:JSON.stringify({...values,request_key:requestKey})});await renderOrganization(areaId);}catch(error){errorMessage(error);button.disabled=false;}
  };
  document.querySelectorAll('[data-organization-run]').forEach(form=>form.onsubmit=async event=>{
    event.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;
    const areas=[...form.querySelectorAll('[data-group]')].filter(group=>group.querySelector('[name=include]').checked).map(group=>({name:group.querySelector('[name=area_name]').value,description:group.querySelector('[name=description]').value,document_ids:[...group.querySelectorAll('[name=document]:checked')].map(input=>input.value)}));
    try{if(!areas.length)throw new Error('Selecione pelo menos uma área para aplicar');await api('/api/runs/'+form.dataset.organizationRun+'/organization/approve',{method:'POST',body:JSON.stringify({areas})});await refresh();await renderOrganization(areaId);}catch(error){errorMessage(error);button.disabled=false;}
  });
  document.querySelectorAll('[data-reject-organization]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await api('/api/runs/'+button.dataset.rejectOrganization+'/reject',{method:'POST',body:'{}'});await renderOrganization(areaId);}catch(error){errorMessage(error);button.disabled=false;}});
  bindDocuments();
}

async function renderPersonalization(selectedArea){
  await renderPersonalizationPage({state,api,esc,pageHead,bindDocuments,errorMessage,refresh},selectedArea);
}

async function aiPanel(panel){
  const s=await api('/api/ai/config');if(!panel.isConnected)return;
  panel.innerHTML='<form id="ai-form" class="form"><label><span><input name="enabled" type="checkbox" style="width:auto" '+(s.enabled?'checked':'')+'> Ativar IA nesta instalação</span></label><label>Endereço base da API<input name="endpoint" type="url" value="'+esc(s.endpoint)+'" placeholder="https://provedor.example/v1"></label><label>Modelo<input name="model" value="'+esc(s.model)+'"></label><label>Chave própria<input name="api_key" type="password" autocomplete="new-password" placeholder="'+(s.has_key?'Já configurada; deixe vazio para manter no mesmo destino':'Informe sua chave')+'"></label><label>Chamadas por dia (UTC)<input name="daily_call_limit" type="number" min="1" max="1000" value="'+s.daily_call_limit+'" required></label><label>Orçamento diário estimado em US$ (opcional)<input name="daily_budget_usd" type="number" step="any" min="0.000001" max="1000" value="'+esc(s.daily_budget_usd)+'"></label><details><summary>Opções avançadas: preços para estimar e limitar o custo</summary><div class="grid grid-2"><label>US$/milhão de tokens de entrada<input name="input_usd_per_million" type="number" step="any" min="0" max="1000" value="'+esc(s.input_usd_per_million)+'"></label><label>US$/milhão de tokens de saída<input name="output_usd_per_million" type="number" step="any" min="0" max="1000" value="'+esc(s.output_usd_per_million)+'"></label></div><p class="subtle">Para aplicar um orçamento estimado, informe os dois preços. Sem preços, o custo continua desconhecido.</p></details><p class="subtle">Preços são informados por você, na mesma moeda. Reserva estimada para até 32.768 tokens de entrada e 1.000 de saída; falhas sem uso conhecido mantêm a reserva. Isso não é confirmação de cobrança. Defina também limite no provedor; assinatura de chat não inclui crédito de API. Chave salva nesta instalação em arquivo protegido, acessível ao administrador.</p><button class="btn primary" type="submit">Salvar configuração</button><p id="ai-saved" role="status"></p></form>';
  guideAI(panel.querySelector('#ai-form'),s,api);
  panel.querySelector('#ai-form').onsubmit=async event=>{event.preventDefault();const form=event.currentTarget;const values=Object.fromEntries(new FormData(form));values.enabled=form.elements.enabled.checked;values.daily_call_limit=Number(values.daily_call_limit);values.api_key=values.api_key||null;for(const key of ['daily_budget_usd','input_usd_per_million','output_usd_per_million'])values[key]=values[key]||null;try{const saved=await api('/api/ai/config',{method:'PUT',body:JSON.stringify(values)});form.elements.api_key.value='';form.dispatchEvent(new CustomEvent('ai-saved',{detail:saved}));panel.querySelector('#ai-saved').textContent='Configuração salva. Nenhuma chamada foi feita.';}catch(error){errorMessage(error);}};
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
    const editing=Boolean(form.dataset.areaId);
    await api('/api/areas'+(editing?'/'+form.dataset.areaId:''), { method: editing?'PUT':'POST', body: JSON.stringify(Object.fromEntries(new FormData(form))) });
    form.reset();
    document.querySelector("#area-dialog").close();
    await refresh();
    renderShell();
    navigate("areas");
    showToast(editing?'Área atualizada':'Área criada');
  } catch (error) { errorMessage(error); }
}

boot();

