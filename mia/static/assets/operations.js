export async function renderOperations({api, esc, pageHead, errorMessage}) {
  const container = document.querySelector('#content');
  container.innerHTML = pageHead('SUA INSTALAÇÃO', 'Operação e atualização') + '<section id="operations-panel" class="card">Carregando…</section>';
  const panel = document.querySelector('#operations-panel');
  const status = await api('/api/operations');
  if (!panel.isConnected) return;
  panel.innerHTML = '<h2>Versão em execução: '+esc(status.app_version)+'</h2>'+
    '<p>'+(status.managed?'Instalação nativa gerenciada.':'Instalação manual ou Docker.')+'</p>'+
    (status.release?'<p style="overflow-wrap:anywhere">Versão instalada: '+esc(status.version)+' · Identificador: '+esc(status.release)+'</p>':'')+
    (status.recovery_required?'<p role="alert">Há uma operação incompleta ou estado indisponível. Use o comando de recuperação no computador da instalação antes de outra atualização. Preserve dados e snapshots.</p>':'<p>Nenhuma recuperação pendente reportada.</p>')+
    '<p>'+esc(status.instructions)+'</p>'+
    '<button class="btn" id="operation-refresh">Atualizar estado</button>'+
    '<h2>Atualizar com segurança</h2><ol><li>Escolha uma versão e confira sua origem. Termine as consultas em andamento e baixe um backup para outro disco.</li><li>No computador onde instalou a Mia, use o gerenciador nativo ou o procedimento Docker documentado. A instalação manual atual continua disponível.</li><li>O gerenciador prepara a versão antes de parar o serviço, guarda um snapshot privado e verifica a versão por HTTP. Se falhar, recupera em um novo diretório, preservando os dados da tentativa.</li><li>Entre novamente quando necessário e confira uma tarefa, fonte e acesso conhecidos.</li></ol>'+
    '<h2>Recuperar ou voltar à versão anterior</h2><p>O retorno usa o snapshot anterior à atualização. As alterações posteriores ficam preservadas em separado, mas não aparecem no banco restaurado. Revise essa diferença antes de confirmar um rollback. Nunca use código antigo diretamente sobre um banco migrado.</p>'+
    '<p>As instruções de instalação, serviço e comandos ficam no guia <strong>docs/OPERATIONS.md</strong> da sua distribuição. Atualizações e alterações de rede são ações explícitas no computador da instalação.</p>'+
    '<p class="subtle">Esta tela consulta estado. Não baixa versões nem executa comandos. Snapshots de operação incluem configuração e possíveis credenciais, sem criptografia; proteja e guarde cópia fora da máquina. Não há cópia externa automática.</p>';
  panel.querySelector('#operation-refresh').onclick = () => renderOperations({api, esc, pageHead, errorMessage}).catch(errorMessage);
}
