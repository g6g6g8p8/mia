export async function renderBackups({api, esc, pageHead, errorMessage}) {
  const container=document.querySelector('#content');
  container.innerHTML=pageHead('PROTEÇÃO DOS DADOS','Backups')+'<section id="backup-panel" class="card">Carregando…</section>';
  const panel=document.querySelector('#backup-panel');
  const s=await api('/api/backups');
  if(!panel.isConnected)return;
  const stamp=value=>value?new Date(value).toLocaleString():'Ainda não realizado';
  panel.innerHTML='<p>Cópias locais do banco: fontes, tarefas, contexto e histórico. Não incluem chaves de IA nem configurações da máquina. Baixe uma cópia e guarde fora deste computador.</p>'+
    '<form id="backup-form" class="form"><label><span><input name="enabled" type="checkbox" style="width:auto" '+(s.enabled?'checked':'')+'> Fazer backup automático a cada 24 horas</span></label><label>Quantas cópias manter<input name="keep" type="number" min="1" max="30" required value="'+s.keep+'"></label><p class="subtle">Funciona enquanto a Mia está aberta no servidor. Ao iniciar, verifica se há backup vencido. A primeira verificação ocorre em até um minuto. Depois de uma nova cópia válida, remove as cópias automáticas mais antigas acima deste limite; o mesmo limite vale para “Criar backup agora”. Backups manuais feitos por comando ficam fora desta retenção.</p><button class="btn primary">Salvar política de backup</button></form>'+
    '<p>Último backup válido: '+esc(stamp(s.last_success))+'</p><p>Última tentativa: '+esc(stamp(s.last_attempt))+'</p>'+(s.error?'<p role="alert">'+esc(s.error)+'</p>':'')+
    '<button class="btn" id="backup-now">Criar backup agora</button> <button class="btn" id="backup-refresh">Atualizar estado</button><p id="backup-feedback" role="status"></p><h2>Cópias disponíveis</h2>'+
    (s.files.length?'<ul>'+s.files.map(f=>'<li style="overflow-wrap:anywhere"><a href="/api/backups/'+encodeURIComponent(f.name)+'">Baixar '+esc(f.name)+'</a> · '+Math.ceil(f.bytes/1024)+' KB</li>').join('')+'</ul>':'<p>Nenhuma cópia criada por esta tela.</p>')+
    '<h2>Restaurar</h2><p>A restauração ainda é por comando em diretório novo e vazio. Ela invalida sessões antigas; entre novamente e reconfigure sua IA. Não sobrescreva a instalação ativa.</p><p class="subtle">As cópias contêm dados pessoais e hash de senha, sem criptografia. Cópia no mesmo disco não protege contra perda do disco. A Mia não envia backups a serviços externos.</p>';
  const refresh=()=>renderBackups({api,esc,pageHead,errorMessage});
  panel.querySelector('#backup-form').onsubmit=async event=>{
    event.preventDefault();const form=event.currentTarget;
    try{await api('/api/backups',{method:'PUT',body:JSON.stringify({enabled:form.elements.enabled.checked,keep:Number(form.elements.keep.value)})});await refresh();}catch(error){errorMessage(error);}
  };
  panel.querySelector('#backup-refresh').onclick=()=>refresh().catch(errorMessage);
  panel.querySelector('#backup-now').onclick=async event=>{
    event.currentTarget.disabled=true;
    panel.querySelector('#backup-feedback').textContent='Criando e verificando a cópia…';
    try{await api('/api/backups',{method:'POST'});await refresh();}
    catch(error){await refresh();errorMessage(error);}
  };
}
