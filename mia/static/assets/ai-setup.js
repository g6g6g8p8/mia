// Guidance only: the server remains responsible for destination and key rules.
export function guideAI(form, settings, api) {
  const destination = form.elements.endpoint;
  const enabled = form.elements.enabled;
  const key = form.elements.api_key;
  const model = form.elements.model;
  const choices = document.createElement('section');
  choices.innerHTML = '<label for="ai-connection">Como você quer conectar a IA?</label>' +
    '<select id="ai-connection"><option value="none">Continuar sem IA</option>' +
    '<option value="openai">OpenAI — conexão direta</option>' +
    '<option value="compatible">Outro serviço ou gateway compatível</option>' +
    '<option value="local">Servidor de IA nesta máquina</option></select>' +
    '<p id="ai-guide" class="subtle"></p>' +
    '<p class="subtle">Nenhum gateway é obrigatório. Salvar não envia seus dados nem testa o modelo.</p>';
  form.prepend(choices);
  const probe = document.createElement('section');
  probe.innerHTML = '<p class="subtle">Verificar consulta apenas o catálogo do destino salvo, com a chave salva. Não envia notas, não gera texto e não verifica saldo ou cobrança.</p><button type="button" class="btn" id="ai-check">Verificar conexão salva</button><p role="status" id="ai-check-result"></p>';
  form.append(probe);
  const check = probe.querySelector('button');
  const status = probe.querySelector('[role="status"]');
  let saved = settings;
  let dirty = false;
  let checking = false;
  function refreshCheck() { check.disabled = checking || dirty || !saved.endpoint || !saved.model; }
  function changed() {
    dirty = true;
    status.textContent = 'Salve as alterações antes de verificar a conexão.';
    refreshCheck();
  }
  form.addEventListener('input', changed);
  form.addEventListener('change', changed);
  form.addEventListener('ai-saved', event => {
    saved = event.detail;
    dirty = false;
    status.textContent = '';
    refreshCheck();
  });
  check.onclick = async () => {
    const snapshot = saved;
    checking = true;
    refreshCheck();
    status.textContent = 'Consultando catálogo de ' + saved.endpoint + '…';
    try {
      const result = await api('/api/ai/connection', {method: 'POST', body: JSON.stringify({endpoint: saved.endpoint, model: saved.model})});
      if (!dirty && saved === snapshot) status.textContent = result.endpoint + ' — ' + result.message;
    } catch (error) {
      if (!dirty && saved === snapshot) status.textContent = error.message;
    } finally { checking = false; refreshCheck(); }
  };
  refreshCheck();
  const select = choices.querySelector('select');
  const help = choices.querySelector('#ai-guide');
  const classify = () => {
    if (!enabled.checked) return 'none';
    if (destination.value.replace(/\/$/, '') === 'https://api.openai.com/v1') return 'openai';
    try {
      if (['localhost', '127.0.0.1', '[::1]', 'host.docker.internal'].includes(new URL(destination.value).hostname)) return 'local';
    } catch (_) { /* Incomplete addresses are validated when saving. */ }
    return 'compatible';
  };
  const explanations = {
    none: 'Traga suas fontes, busque e escolha o que retomar sem modelo. Suas configurações ficam disponíveis para ativar depois.',
    openai: 'Endereço preenchido para conexão direta. Informe sua chave de API e o identificador de um modelo com suporte a ferramentas. A assinatura de chat não configura esta conexão. A compatibilidade do modelo ainda precisa ser validada.',
    compatible: 'Informe o endereço base fornecido pelo serviço, incluindo /v1 quando necessário, sem /chat/completions. Esta versão exige Chat Completions, ferramentas e max_completion_tokens. APIs com outro protocolo ainda não são suportadas. OpenRouter é apenas uma opção.',
    local: 'Instale e inicie um servidor compatível na máquina onde a Mia roda. Informe endereço, porta e modelo; chave depende do servidor. “Local” é o computador da Mia, não o celular. Em Docker, localhost é o contêiner. A Mia ainda não instala modelos nem garante sua qualidade.'
  };
  function explain() {
    help.textContent = explanations[select.value];
    destination.required = enabled.checked;
    model.required = enabled.checked;
  }
  select.value = classify();
  explain();
  select.onchange = () => {
    const mode = select.value;
    enabled.checked = mode !== 'none';
    if (mode !== 'none') {
      const next = mode === 'openai' ? 'https://api.openai.com/v1' : '';
      // A different destination must never inherit a typed credential/model.
      if (next !== destination.value) {
        destination.value = next;
        key.value = '';
        model.value = '';
      }
      destination.placeholder = mode === 'local' ? 'http://127.0.0.1:porta/v1' : 'https://provedor.example/v1';
      key.placeholder = 'Informe a chave deste destino, se necessária';
    }
    explain();
  };
  enabled.addEventListener('change', () => { select.value = classify(); explain(); });
  destination.addEventListener('input', () => {
    key.value = '';
    key.placeholder = destination.value.replace(/\/$/, '') === settings.endpoint && settings.has_key
      ? 'Já configurada; deixe vazio para manter no mesmo destino' : 'Informe a chave deste destino, se necessária';
    select.value = classify();
    explain();
  });
}
