# Mia Demo a13 — implementação e validação

14/10/2026. Implementação de [MAC-DEMO.md](MAC-DEMO.md), na branch `feat/invite-only-mac-demo`. A a13 contém o cliente nativo e sua infraestrutura de distribuição; não está liberada para convidados enquanto assinatura, publicação e aceites reais estiverem abertos.

## Implementado

- **App Mac:** SwiftUI/AppKit + WKWebView com janela própria, menus, seletores de arquivos/pastas, exportação e sessão separada por instalação. Destinos locais, SSH e HTTPS têm identidade/origem verificadas. Mudança de porta recria o cliente web e troca de destino descarta aprovações da instalação anterior.
- **Neste Mac:** plano legível e confirmação por hash, runtime/dependências offline, instalação privada vazia, serviço de usuário, retomada explícita e recuperação de interrupção. Dados e runtime ficam fora do `.app`. Ativação launchd confere caminho, programa e argumentos do job antes de repetir uma operação interrompida.
- **Meu servidor:** preflight e instalador Ubuntu 24.04 amd64, fingerprint SSH com chaves alteradas/revogadas bloqueadas, runtime verificado, diretório novo e túnel supervisionado. Precisa de SSH por chave/agente, espaço, serviço de usuário disponível e linger já habilitado. Falta de pré-requisito pausa o percurso; não usa sudo, substitui Python global ou altera outros serviços.
- **Primeiro proprietário:** instalações feitas pelo app exigem capacidade privada entregue por IPC/SSH e cookie HttpOnly antes de criar acesso. Nenhum token aparece em API pública, URL ou lista de conexões. Loopback sozinho não é tratado como autorização de outro usuário do sistema.
- **Contexto:** no app, onboarding por fontes → foco → Hoje, sem chave obrigatória. O destino informado pelo backend prevalece sobre parâmetros visuais do cliente. Importação e autorização continuam nas APIs normais.
- **Convites:** portal separado, resgate único idempotente após resposta perdida, expiração/revogação e download retomável. Tokens ficam no fragmento da URL e em hashes no armazenamento privado. A administração é CLI local; não há endpoint público para emitir convites.
- **Atualizações:** Sparkle 2.10.0 para substituir app assinado; feed Ed25519 para backend, preparação autenticada, plano revisado, snapshot e recuperação pelo gerenciador estável. Cliente e backend têm versões/ações distintas. Sem canal/chave pública no bundle, o estado é não configurado; nenhuma origem de atualização é inventada.

A primeira entrega da atualização local mantém o runtime/bootstrap compatíveis. Trocar sua arquitetura ou contrato exige migração específica; não se anuncia isso como atualização simples. Atualização remota do backend pelo assistente ainda não foi implementada e a interface informa essa limitação.

## Evidência obtida

O CI nativo compila e executa 21 testes Swift em macOS 15 arm64 e Intel. Os testes incluem contratos/limites do subprocesso, origem, cookie privado e estado de aprovação/reconexão. Isso não é um teste visual de instalação em Mac limpo nem de login/suspensão.

Na revisão `6d67578`, o [CI nativo](https://github.com/g6g6g8p8/mia/actions/runs/38592491512) gerou os DMGs internos arm64 e Intel e verificou sua integridade com `hdiutil verify`. O companion Linux e os dois jobs de compilação/testes também passaram. Os recibos registram o inventário final do app e conferem a cópia usada no DMG. Esses artefatos não foram assinados nem notarizados.

A suíte Python passou com **508 testes** na revisão `585d2d2`, com um aviso de depreciação do Starlette. O ícone nativo reutiliza a identidade SVG existente; o pacote-fonte conserva os assets e a revisão fixada do Sparkle. O resultado dos DMGs deve ser conferido no PR/CI da revisão escolhida.

O ensaio de pacotes a11 → a13 passou instalação offline, atualização com dados preservados, falha de inicialização, interrupção do journal, recuperação explícita, rollback em dados novos e encerramento abrupto do supervisor. Usou processos Linux, HTTP loopback e dados sintéticos; não certifica launchd/systemd, boot ou suspensão de um dispositivo real.

Chromium passou o percurso desktop com destino local, remoto, desconhecido e divergente, incluindo autenticação, revisão/importação, foco/Hoje, reabertura e zero chamadas de IA. Ensaios anteriores a13 também passaram o corpus sintético de 1.500 notas/1.000 autorizadas e controles de consentimento/revogação/orçamento. Não equivalem a WKWebView físico ou utilidade com o vault do participante.

O companion Linux passa instalação offline, primeiro acesso protegido, rejeição sem capacidade, criação autorizada do proprietário, reinício e integridade do runtime. Casos de teste executam o instalador/probe incorporados; não há alegação de instalação SSH/systemd no servidor pessoal. Nenhum convite real foi emitido e nenhum host pessoal foi alterado por esta implementação.

O empacotamento revelou colisões entre nomes de terminais Linux e APFS. A preparação omite somente o prefixo opcional `python/share/terminfo` antes da extração, com índice/hash/contagem registrados. Arquivos do Python, bibliotecas e avisos retidos permanecem idênticos aos originais autenticados. Hash dos arquivos upstream, TLS, assinatura e verificações de caminho continuam obrigatórios.

## Build de desenvolvimento e produção

O pipeline [.github/workflows/mac-demo.yml](../.github/workflows/mac-demo.yml) prepara o companion Linux e compila/testa Mac arm64 e Intel. Artefatos `Mia-UNSIGNED-INTERNAL-*` são internos, sem aprovação para beta. A publicação de um DMG no CI não o transforma em app assinado/notarizado.

Para o responsável pelo build, em Mac nativo com ferramentas disponíveis:

```bash
scripts/build_macos_app.sh --preflight
scripts/build_macos_app.sh --output /destino/novo --remote-artifact /companion/revisado --unsigned
```

O script inclui os runtimes/avisos, verifica novamente bytes upstream e wheels, roda testes Swift e instala/inicia o backend offline com dados sintéticos. O aceite de runtime não executa código de outra arquitetura.

Para produção, usar uma identidade **Developer ID Application** e perfil de notarização que já existam no Keychain do Mac de build. O modo assinado exige ambos, verifica códigos aninhados, aguarda aceitação da notarização e confere o ticket; não há instrução de contorno do Gatekeeper. Somente o executável Python recebe a permissão para carregar bibliotecas sem Developer ID, necessária às extensões dos wheels verificados; o app e os helpers mantêm o hardened runtime. O ensaio offline roda depois da assinatura, e o recibo externo registra os bytes finais do app e verifica a integridade do DMG após notarização/ticket. Esses passos assinados ainda não foram executados com credenciais reais.

Metadados Apple usam versão numérica de três componentes e sufixos a/b/fc; a versão original do backend permanece separada. O canal público de atualização entra em `--release-channel` com URL e chave pública revisadas; chaves privadas/certificados/senhas ficam fora do Git, do bundle e do chat.

Depois de cada troca do app, a atualização do backend incluído continua uma ação revisada com snapshot. Recuperação não abre código antigo sobre banco novo. O código não faz cópia de banco vivo por iCloud/Drive nem sincronização offline entre instalações.

## Publicar a rodada privada

Após os aceites, preparar o artefato correto, SHA256, serviço separado em loopback e uma origem HTTPS. A CLI administrativa é `scripts/demo_distribution.py --state /pasta/privada ...`; `serve` usa porta 8130 por padrão, `issue` e `revoke` só rodam pelo operador. Resultados de emissão contêm convites privados: guardar fora do repositório e não anexar ao relatório.

O proprietário decide os destinatários e envia os links. Convite controla nossa distribuição oficial, não a licença Apache nem o acesso ao conteúdo de uma instância. Publicação do portal, canal de atualização, credenciais Apple e convite de pessoas ainda exigem seus recursos reais; não foram simulados como concluídos.

Antes dos convites: Mac limpo por arquitetura oferecida; abrir/instalar/importar/Hoje/reabrir pelo app; serviço após login/suspensão; restauração externa; atualização assinada e falha/recuperação; SSH/boot reais se servidor for oferecido. Registrar ajuda e cenários não executados conforme [PILOT.md](PILOT.md). App iPhone, Drive recorrente e sync offline permanecem posteriores.
