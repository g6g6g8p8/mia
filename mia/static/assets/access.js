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
    '<h2>Manter e recuperar o acesso</h2><p>Antes de mudar a rede, mantenha acesso ao computador onde a Mia roda e faça backup. Salvar “Só neste computador” aqui não fecha portas ou túneis já configurados. Para desativar acesso externo, desative também a rota ou proxy na máquina/roteador.</p>';
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
}
