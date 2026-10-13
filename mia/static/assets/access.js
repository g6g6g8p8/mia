export async function renderAccess({api, esc, pageHead, errorMessage}) {
  const container = document.querySelector('#content');
  container.innerHTML = pageHead('SUA INSTALAÇÃO', 'Acesso à Mia') + '<section id="access-panel" class="card">Carregando…</section>';
  const panel = document.querySelector('#access-panel');
  const settings = await api('/api/access/config');
  if (!panel.isConnected) return;
  const https = location.protocol === 'https:';
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  panel.innerHTML = '<h2>Onde você quer usar a Mia?</h2><p>Não exige Tailscale nem conta central. Este assistente guarda sua preferência e orienta a preparação; ainda não altera rede, domínio ou certificados.</p>' +
    '<form id="access-form" class="form"><label for="access-mode">Forma de acesso</label><select id="access-mode" name="mode"><option value="computer">Só neste computador</option><option value="lan">Outros dispositivos na mesma rede</option><option value="remote">Também fora de casa ou do escritório</option></select>' +
    '<div id="access-steps"></div><label for="access-address">Endereço HTTPS preparado (opcional)</label><input id="access-address" name="address" type="url" placeholder="https://mia.seu-dominio.example" value="'+esc(settings.address)+'"><p class="subtle">Salvar o endereço não o publica e não confirma que ele funciona. Deixe vazio enquanto prepara a rede.</p><button class="btn primary">Salvar preferência de acesso</button><p id="access-saved" role="status"></p></form>' +
    '<h2>Diagnóstico desta sessão</h2><p style="overflow-wrap:anywhere">Endereço atual: '+esc(location.origin)+'</p><ul><li>'+ (https ? 'Navegador conectado por HTTPS.' : loopback ? 'Acesso HTTP local neste computador.' : 'Acesso HTTP fora de loopback: prepare HTTPS antes de usar dados pessoais.') +'</li><li>'+ (settings.secure_cookie ? 'Cookie de acesso configurado para HTTPS.' : 'Cookie sem exigência de HTTPS. Antes do acesso em rede, ative MIA_COOKIE_SECURE=true e reinicie a instalação.') +'</li></ul><button class="btn" id="access-check">Verificar conexão atual</button><p id="access-result" role="status"></p><p class="subtle">Este diagnóstico não verifica firewall, certificado de outro endereço nem acesso de fora da rede.</p>' +
    '<h2>Preparar mudanças para revisão</h2><p>O plano usa a forma de acesso e o endereço preenchidos acima. Gera arquivos e mostra exatamente as mudanças sugeridas, sem salvar preferência, abrir portas ou executar comandos. Caddy é uma opção de proxy HTTPS; você pode escolher outro.</p>' +
    '<form id="access-plan-form" class="form"><label for="access-certificate">Certificado do endereço de destino</label><select id="access-certificate" name="certificate"><option value="internal">CA privada (confiar a raiz nos dispositivos)</option><option value="public">Público automático (domínio próprio e rota de entrada)</option></select>' +
    '<label for="access-listener">IP da interface onde o proxy escutará</label><input id="access-listener" name="listen_address" value="127.0.0.1" required><p class="subtle">127.0.0.1 mantém o ensaio local. Para LAN/servidor, informe a interface escolhida. 0.0.0.0 atende todas as interfaces e precisa de revisão de alcance/firewall.</p>' +
    '<label for="access-upstream">Porta HTTP local da Mia</label><input id="access-upstream" name="upstream_port" type="number" min="1" max="65535" value="8123" required>' +
    '<label for="access-recovery">Porta HTTPS de recuperação local</label><input id="access-recovery" name="recovery_port" type="number" min="1024" max="65535" value="8443" required><button class="btn" id="access-plan-button">Preparar plano sem aplicar</button><p id="access-plan-result" role="status"></p></form><div id="access-plan-preview"></div>' +
    '<h2>Manter e recuperar o acesso</h2><p>Antes de mudar a rede, mantenha acesso ao terminal da máquina e faça backup. O plano inclui HTTPS local para recuperação: cookie Secure não permite login por HTTP. Se o proxy falhar, o terminal permite restaurar a configuração anterior e iniciar a Mia somente em loopback. Salvar “Só neste computador” não fecha portas ou túneis existentes. Para desativar acesso externo, remova também a rota ou proxy na máquina/roteador.</p>';
  const form = panel.querySelector('form');
  const mode = form.elements.mode;
  mode.value = settings.mode;
  const instructions = {
    computer: '<ol><li>Abra o endereço local na máquina onde instalou a Mia.</li><li>Endereços localhost e 127.0.0.1 não funcionam no celular para acessar outro computador.</li><li>Não é necessário configurar domínio, VPN ou serviço externo.</li></ol>',
    lan: '<ol><li>Conecte celular e computador à mesma rede.</li><li>Prepare um endereço da máquina acessível nessa rede, com HTTPS confiável. Um serviço limitado a 127.0.0.1 precisa de um proxy acessível à rede.</li><li>Configure firewall e cookie HTTPS na instalação. Ainda exige configuração fora desta tela.</li><li>Abra o endereço no outro dispositivo e entre com sua senha da Mia.</li></ol>',
    remote: '<ol><li>Escolha onde hospedar: sua máquina com rota de entrada ou servidor próprio.</li><li>Prepare domínio/endereço, HTTPS e proxy para a Mia. Não exponha a porta HTTP da aplicação diretamente à internet.</li><li>Se a rede bloquear conexões de entrada (como CGNAT), use uma rota alcançável, servidor próprio ou túnel opcional de sua escolha. Nenhuma marca é obrigatória.</li><li>Ative cookie HTTPS. Teste o endereço pelo celular fora do Wi-Fi antes de considerar concluído.</li></ol>'
  };
  function guide() { panel.querySelector('#access-steps').innerHTML = instructions[mode.value]; }
  mode.onchange = guide;
  guide();
  form.onsubmit = async event => {
    event.preventDefault();
    try {
      await api('/api/access/config', {method:'PUT', body:JSON.stringify(Object.fromEntries(new FormData(form)))});
      panel.querySelector('#access-saved').textContent = 'Preferência salva. A rede não foi alterada.';
    } catch (error) { errorMessage(error); }
  };
  panel.querySelector('#access-check').onclick = async () => {
    const result = panel.querySelector('#access-result');
    result.textContent = 'Verificando…';
    try {
      await api('/api/me');
      result.textContent = 'A Mia respondeu com sua sessão autenticada neste endereço. Teste outros dispositivos separadamente.';
    } catch (error) { result.textContent = 'Não foi possível validar a sessão atual.'; errorMessage(error); }
  };
  const planForm = panel.querySelector('#access-plan-form');
  let planGeneration = 0;
  function invalidatePlan() {
    planGeneration++;
    const preview = panel.querySelector('#access-plan-preview');
    const status = panel.querySelector('#access-plan-result');
    if (preview.textContent || status.textContent) {
      preview.innerHTML = '';
      status.textContent = 'Campos alterados. Prepare um novo plano antes de aplicar mudanças.';
    }
  }
  [form, planForm].forEach(item => {
    item.addEventListener('input', invalidatePlan);
    item.addEventListener('change', invalidatePlan);
  });
  function download(name, content, type = 'text/plain') {
    const url = URL.createObjectURL(new Blob([content], {type}));
    const link = document.createElement('a');
    link.href = url; link.download = name; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  planForm.onsubmit = async event => {
    event.preventDefault();
    const status = panel.querySelector('#access-plan-result');
    const preview = panel.querySelector('#access-plan-preview');
    const button = panel.querySelector('#access-plan-button');
    const generation = ++planGeneration;
    preview.innerHTML = ''; status.textContent = 'Preparando…'; button.disabled = true;
    try {
      const payload = Object.fromEntries(new FormData(planForm));
      payload.mode = mode.value; payload.address = form.elements.address.value;
      payload.upstream_port = Number(payload.upstream_port); payload.recovery_port = Number(payload.recovery_port);
      const plan = await api('/api/access/plan', {method:'POST', body:JSON.stringify(payload)});
      if (!panel.isConnected || generation !== planGeneration) return;
      const list = values => '<ul>' + values.map(value => '<li>'+esc(value)+'</li>').join('') + '</ul>';
      preview.innerHTML = '<h3>Plano preparado · infraestrutura ainda não verificada · acesso ainda não comprovado</h3>' +
        '<h3>Mudanças propostas</h3>' + (plan.changes.length ? list(plan.changes) : '<p>Nenhuma mudança de rede proposta para uso neste computador.</p>') +
        '<h3>Antes de aplicar</h3>' + list(plan.warnings) +
        Object.entries(plan.files).map(([name, content]) => '<h3>'+esc(name)+'</h3><pre style="max-width:100%;overflow:auto">'+esc(content)+'</pre><button class="btn" data-access-file="'+esc(name)+'">Baixar '+esc(name)+'</button>').join('') +
        (plan.commands.length ? '<h3>Aplicação manual no terminal</h3><p>Valide primeiro. Após revisar e autorizar as mudanças locais, use os argumentos abaixo no terminal da instalação. Preserve diretório de dados, ambiente e serviço existente. Esta tela não executa os comandos.</p>' + plan.commands.map(command => '<p>'+esc(command.purpose)+'</p><pre style="max-width:100%;overflow:auto">'+esc(JSON.stringify(command, null, 2))+'</pre>').join('') : '') +
        '<h3>Verificar após aplicar</h3>' + list(plan.checks) + '<h3>Recuperação e desligamento</h3>' + list(plan.recovery) +
        '<button class="btn" id="access-plan-download">Baixar plano completo</button>';
      preview.querySelector('#access-plan-download').onclick = () => download('mia-access-plan.json', JSON.stringify(plan, null, 2), 'application/json');
      preview.querySelectorAll('[data-access-file]').forEach(item => { item.onclick = () => download(item.dataset.accessFile, plan.files[item.dataset.accessFile]); });
      status.textContent = 'Prévia gerada. Preferência, rede e infraestrutura não foram alteradas.';
    } catch (error) { status.textContent = 'Não foi possível preparar o plano. Confira os campos.'; errorMessage(error); }
    finally { button.disabled = false; }
  };
}
