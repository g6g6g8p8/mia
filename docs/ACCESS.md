# Acesso à Mia

Em **Sistema → Acesso à Mia**, escolha computador, rede local ou acesso remoto. O assistente salva a preferência e um endereço HTTPS opcional, mostra orientações por cenário e verifica a sessão autenticada no endereço atual. Nenhuma conta central, VPN ou marca de túnel é obrigatória.

Esta etapa não configura a rede: salvar não abre nem fecha portas, não instala proxy/certificados, não muda domínio e não comprova acesso externo. HTTPS da sessão e configuração de cookie são verificações distintas. Teste o endereço pelo dispositivo de destino; para remoto, teste fora do Wi-Fi da instalação. Não usar o diagnóstico da sessão atual como prova de acesso externo.

As preferências ficam em `MIA_DATA_DIR/access-settings.json` com permissão 0600, fora do repositório e do backup SQLite. São específicas da máquina: após restaurar em outra instalação, revise-as. A API exige proprietário autenticado e aplica a proteção de origem existente. Não há chamadas do servidor ao endereço informado.

Limites: configuração do sistema operacional, domínio, HTTPS e rota de entrada ainda são externas. CGNAT pode exigir outra rota, servidor próprio ou túnel opcional. Mudar a preferência para acesso local não revoga uma publicação externa existente. Para desativar acesso remoto, remova também a rota/proxy configurada no host ou roteador.
