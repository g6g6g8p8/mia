# Mia Demo a14 — implementação e validação

15/10/2026. Implementação de [MAC-DEMO.md](MAC-DEMO.md), na branch `feat/invite-only-mac-demo`. A a14 amplia o cliente nativo, a operação do servidor e a distribuição privada do beta. A revisão integrada e o CI desta revisão ainda precisam concluir. Assinatura Apple, publicação e aceites reais permanecem requisitos para liberar convidados.

## Implementado no código

- **App Mac:** SwiftUI/AppKit + WKWebView com janela própria, menus, seletores de arquivos/pastas, exportação e sessão separada por instalação. Destinos locais, SSH e HTTPS têm identidade/origem verificadas. Mudança de porta recria o cliente web; no SSH, a identidade do armazenamento de sessão permanece vinculada à conexão/instalação, sem depender da porta temporária. Trocar destino descarta aprovações anteriores.
- **Neste Mac:** plano legível e confirmação por hash, runtime/dependências offline, instalação privada vazia, serviço de usuário, retomada explícita e recuperação de interrupção. Dados e runtime ficam fora do `.app`. Ativação launchd confere caminho, programa e argumentos do job antes de repetir uma operação interrompida.
- **Meu servidor:** preflight e instalador Ubuntu 24.04 amd64, fingerprint SSH com chaves alteradas/revogadas bloqueadas, runtime verificado, diretório novo e túnel supervisionado. Precisa de SSH por chave/agente, espaço, serviço de usuário disponível e linger já habilitado. Falta de pré-requisito pausa o percurso; não usa sudo, substitui Python global ou altera outros serviços.
- **Operação remota:** interface para revisar e confirmar snapshot, atualização do backend incluído e recuperação de interrupção. Aprovação vincula conexão, host, instalação, runtime, gerenciador, serviço e estado ativo; o lock confere novamente o estado antes de alterar dados. Transferências e resultados interrompidos deixam journal durável; repetir a mesma operação não duplica seus efeitos. Instalação pausada permanece pausada.
- **Primeiro proprietário:** instalações feitas pelo app exigem capacidade privada entregue por IPC/SSH e cookie HttpOnly antes de criar acesso. Nenhum token aparece em API pública, URL ou lista de conexões. Loopback sozinho não é tratado como autorização de outro usuário do sistema.
- **Contexto:** no app, onboarding por fontes → foco → Hoje, sem chave obrigatória. O destino informado pelo backend prevalece sobre parâmetros visuais do cliente. Importação e autorização continuam nas APIs normais.
- **Convites e Vercel:** código de portal separado, resgate único idempotente após resposta perdida, expiração/revogação e metadados duráveis em Upstash Redis. Operações atômicas guardam hashes das capacidades; não usam SQLite em `/tmp` como persistência de uma função. DMGs ficam em Blob privado e chegam por autorização de leitura de um objeto, válida por até 60 segundos. Downloads grandes não passam pela resposta da função. Provisionamento, quotas gratuitas e publicação reais ainda não foram verificados na conta.
- **Autorização do beta no Mac:** o ticket do portal ativa uma autorização de até 90 dias guardada no Keychain. Ela libera somente downloads/atualizações oficiais; appcast e DMGs oficiais permanecem privados. Expiração ou revogação não desativa biblioteca, exportação ou recuperação da instalação. Nenhum conteúdo pessoal vai para o portal.
- **Atualizações:** Sparkle 2.10.0 substitui o app assinado; feed Ed25519 autentica o backend, com preparação, plano revisado, snapshot e recuperação pelo gerenciador estável. Cliente e backend têm versões/ações distintas. Sem canal/chave pública no bundle, o estado é não configurado; nenhuma origem é inventada.

A atualização do backend mantém o runtime/bootstrap instalados e verifica seus bytes. Assinaturas Apple novas podem alterar timestamps/bytes do runtime incluído no novo app: a compatibilidade compara a proveniência upstream autenticada, conservando o runtime privado antigo e sua verificação exata. Isso não autoriza substituir runtime, arquitetura ou bootstrap. Instalações legadas sem essa proveniência exigem bytes idênticos ou migração específica.

Os serviços passam a iniciar Python com `-I -B`, evitando que o início grave bytecode no runtime imutável. Runtime antigo já alterado não é silenciosamente aceito como confiável; continua exigindo diagnóstico/migração explícita.

## Evidência e limites

A referência anterior **a13** passou 528 testes Python, 21 testes Swift por arquitetura e geração/verificação dos DMGs internos arm64 e Intel. O [CI da revisão `ac65fa5`](https://github.com/g6g6g8p8/mia/actions/runs/38597494351) passou os cinco jobs. Esses DMGs não foram assinados nem notarizados. Os resultados históricos não aprovam automaticamente a a14.

Na a14, **722 testes Python passaram**, incluindo operação remota, manutenção do runtime assinado, autorização de distribuição, Redis real com concorrência/reinício e recibos de publicação. A compilação e a suíte Swift passaram em arm64 e Intel na revisão `1c07800`: 49 testes aprovados e um ensaio WebKit opt-in separado. O empacotamento dessa revisão encontrou uma falha no percurso WebKit; seus ensaios não estão aprovados. Os resultados e a revisão final devem ser conferidos no PR/CI antes de promover um artefato.

Também foram implementados dois ensaios macOS com o runtime final do app: WKWebView real com autenticação, importação/revisão/foco/Hoje, e serviço launchd real em diretório sintético isolado. O build exige esses ensaios e registra seus resultados no recibo. **Implementar o ensaio não significa que esta revisão já passou em Mac.** O seletor de pasta usa fixture do delegate; clique humano no NSOpenPanel, instalação em Mac limpo, login do sistema, boot e suspensão continuam aceites separados.

O ensaio Linux a14 instalou offline, criou proprietário/tarefa/fonte sintéticos, executou snapshot e atualização preservando os dados e a pausa, usando o bootstrap corrigido. Usou processos e HTTP reais, com identidade Ubuntu/systemd/linger simulada no ambiente de desenvolvimento; não é instalação SSH/systemd em servidor pessoal. Não comprova migração automática do bootstrap a13 original.

Ensaios históricos a13 passaram atualização a11 → a13 com recuperação/rollback, Chromium no percurso desktop e corpus de 1.500 notas/1.000 autorizadas, sem chamadas de IA. Não equivalem a utilidade com o vault do participante. Nenhum convite real foi emitido e nenhum Mac, servidor ou vault pessoal foi alterado por esta implementação.

A preparação do companion Linux omite somente o prefixo opcional `python/share/terminfo` antes da extração, para evitar colisões com APFS, com índice/hash/contagem registrados. Arquivos Python, bibliotecas e avisos retidos conservam os bytes upstream autenticados.

## Build e publicação

O pipeline [.github/workflows/mac-demo.yml](../.github/workflows/mac-demo.yml) prepara o companion Linux e compila/testa Mac arm64 e Intel. Artefatos `Mia-UNSIGNED-INTERNAL-*` são internos. Publicar um DMG no CI não o transforma em distribuição para participantes.

Para o responsável pelo build, em Mac nativo com ferramentas disponíveis:

```bash
scripts/build_macos_app.sh --preflight
scripts/build_macos_app.sh --output /destino/novo --remote-artifact /companion/revisado --unsigned
```

O script inclui runtimes/avisos, verifica bytes upstream e wheels, roda testes Swift, instala/inicia o backend offline e exige os ensaios WKWebView/launchd com dados sintéticos. Não executa runtime de outra arquitetura. O empacotador repete somente o erro nativo exato `Resource busy`, em no máximo três tentativas, sem relaxar a verificação final de integridade do DMG.

Produção exige identidade **Developer ID Application** e perfil de notarização já presentes no Keychain do Mac de build. O modo assinado verifica códigos aninhados, aguarda aceitação Apple e confere o ticket. Somente o executável Python recebe a permissão para carregar extensões dos wheels verificados; app/helpers mantêm hardened runtime. O ensaio offline ocorre depois da assinatura. Esses passos ainda não foram executados com credenciais reais; o proprietário informou não possuir Apple Developer.

O recibo vincula DMG, inventário final do app, fonte limpa/revisão, wheels e ensaios nativos. O publicador exige atestação assinada gerada após verificações Apple reais do DMG montado somente para leitura, além de um registro humano de aceite para o SHA exato e as arquiteturas/modalidades oferecidas. Campos JSON autodeclarados não substituem essas provas. O recibo automatizado mantém `consumer_distribution_ready=false`; aceites de produto não são inventados pelo build.

O canal revisado entra em `--release-channel`, incluindo URL pública do portal e chaves públicas, sem certificados/senhas/chaves privadas. O app usa autorização privada para o appcast e para obter a leitura temporária do DMG; pacotes de código-fonte Apache e feeds assinados do backend podem ser públicos. Credenciais da distribuição não são encaminhadas a origens arbitrárias.

A escolha é **hospedagem externa na Vercel gratuita**, não macserver/Funnel. O kit mantém o contexto pessoal fora da hospedagem e usa armazenamento durável para convites. A elegibilidade Hobby, quotas atuais, integração gratuita Upstash e stores Blob precisam ser conferidos na conta antes de provisionar/publicar; nada nesta execução contratou recursos pagos. Ferramentas/autorização Vercel ainda não foram expostas nesta sessão, portanto não há URL publicada. Procedimento e limites em [BETA-PUBLICATION.md](BETA-PUBLICATION.md).

O proprietário escolhe destinatários e envia links individuais depois dos aceites. Antes dos convites: Mac limpo por arquitetura oferecida; instalar/importar/Hoje/reabrir pelo app; login/suspensão; restauração externa; atualização assinada e falha/recuperação; SSH/boot reais se servidor for oferecido. Registrar ajuda e cenários não executados conforme [PILOT.md](PILOT.md). App iPhone, Drive recorrente e sync offline permanecem posteriores.
