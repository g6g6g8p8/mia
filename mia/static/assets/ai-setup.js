// Guidance only: the server remains responsible for destination and key rules.
export function guideAI(form, settings) {
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
    none: 'Use tarefas, importação e busca sem modelo. Suas configurações ficam disponíveis para ativar depois.',
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
