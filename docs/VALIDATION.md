# Validação do M1

## Rodada cloud — 0.2.0a11

Estado: alpha técnica revisada; marcos externos continuam em [RELEASE-CHECKLIST.md](RELEASE-CHECKLIST.md). Dados exclusivamente sintéticos e instalações descartáveis. Nenhuma nova chamada paga ou acesso à instalação pessoal do proprietário. O total real conhecido permanece 17 chamadas/US$ 0.0045882598.

- **Linux de desenvolvimento:** Debian 13.6 x86_64, Python 3.12.14; 141 testes passaram, nenhum teste ignorado. Aviso não bloqueante de `BlockingPortal` na dependência Starlette/AnyIO. Inclui revisão de tarefa, aprovação concorrente/única, exportação/restauração e proteção de origem; testes operacionais verificam snapshot, dados posteriores, falha de startup, journal durável, recuperação repetida, banco ausente, symlink e identidade de processo.
- **Processos reais:** `scripts/native_lifecycle.py` instala baseline público `7a026c2` (0.2.0a10) e candidato 0.2.0a11 em venvs novos, fora da fonte. Verifica instalação vazia, importação/fonte, objetivo/contexto, reinício, reserva interrompida sem reenvio, update/HTTP/assets, tarefa editada com provedor HTTP local determinístico e replay, startup falho, recuperação, retorno e SIGKILL de supervisor com identificação/parada do filho. Rodadas com wheelhouse existente e download oficial temporário passaram; ambas instalaram dependências offline depois da obtenção. Isso é processo/pacote real, não modelo real nem boot de Mac/Ubuntu completo.
- **Ubuntu isolado:** Ubuntu 24.04 em container, Python 3.12.3/venv novos; 141 testes, upgrade/restauração da 0.2.0a3 e HTTP/assets do pacote instalado passaram com rede desligada após preparação. Dependências obtidas de wheelhouse verificado, apt com verificação normal. Revisão de avisos instalada passou. A tentativa inicial de pip pela rede falhou por confiança no certificado do proxy cloud; nenhuma verificação TLS foi desabilitada. O cache é opção explícita do runner, não alteração de pins.
- **Navegador:** Playwright 1.55.0 e Chromium 154.0.8037.57 do sistema, via `MIA_BROWSER_EXECUTABLE`. Smoke desktop/mobile, onboarding/importação/conflitos/pausa, harness/revisão de tarefas/organização/personalização e operações/acesso passaram sem erro JavaScript ou transbordamento horizontal a 390 px. Estado gerenciado/corrupto na tela foi fixture de renderização; o lifecycle separado valida o gerenciador real. Download do Chromium empacotado foi bloqueado por domínio no cloud; não foi substituído por navegador de origem não verificada.
- **HTTPS isolado:** Caddy 2.10.2, arquivo gerado por Mia e CA local explicitamente confiada só no cliente de teste. Sete verificações passaram: validação do artefato, instalação vazia/sessão HTTPS, origem permitida/recusada, cookie Secure fora de HTTP, recuperação local/logout/login, rejeição de certificado não confiado e encerramento dos processos temporários. O binário Caddy foi conferido contra checksum oficial; não houve instalação de CA global, DNS/firewall/túnel ou listener público.
- **Distribuição:** wheel/sdist e pacote instalado fora da fonte conferidos, 279 textos e inventários/aviso geral preservados integralmente; builds com setuptools mínimo 75 e atual 84 passaram. O escopo e as limitações estão em [DEPENDENCIES.md](DEPENDENCIES.md). Verificação de padrões selecionados de chave privada/token em 363 blobs únicos do histórico, antes dos commits finais, encontrou zero ocorrências; isso não é auditoria completa de segredos.

A revisão independente encontrou e motivou correções de precedência de configuração, corrida entre startup e update, identidade de release/data/processo, janela de filho não identificado, recuperação repetida e caminhos por symlink. Nove testes adversariais incluem SIGKILL real antes/depois do registro do filho e preservação de dados após interrupção da finalização. Nenhum bloqueio ficou identificado no código revisado; essa conclusão não certifica segurança para toda infraestrutura.

Reprodução (a partir da raiz do checkout; somente fixtures descartáveis):

```bash
.venv/bin/python -m pytest
.venv/bin/python scripts/package_smoke.py
.venv/bin/python scripts/native_lifecycle.py
MIA_BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python scripts/browser_smoke.py
MIA_BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python scripts/browser_onboarding.py
MIA_BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python scripts/browser_harness.py
MIA_BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python scripts/browser_operations.py
.venv/bin/python scripts/https_access_rehearsal.py --caddy /caminho/do/caddy-verificado
.venv/bin/python scripts/check_distribution.py --installed
MIA_VALIDATION_WHEELHOUSE=/caminho/dos/wheels-verificados bash scripts/clean_ubuntu.sh 2d43f085c8e9388202ec3d3914f1da20a4a14b9a
```

O caminho do Chromium e o wheelhouse são específicos da máquina. Sem wheelhouse, o runner Ubuntu usa a instalação de rede normal e exige confiança TLS correta; sem `MIA_BROWSER_EXECUTABLE`, Playwright exige seu Chromium instalado. Boot/systemd/launchd, rede LAN em segundo dispositivo, HTTPS público, provedor direto, fontes reais e participantes continuam não executados nesta rodada. Nenhum resultado simulado foi marcado como esses aceites.

Registro de validação reproduzível do protótipo instalável, sem dados pessoais.

## Ambiente

- Data: 11/10/2026
- Host: Ubuntu, arquitetura x86_64
- Docker Engine: 29.1.3
- Docker Compose: 2.40.3
- Revisão testada: `81e27fab01225da15c45bfdbdfaf4b47cd6e9836`
- Exposição: somente `127.0.0.1:8123`

## Resultado

| Verificação | Resultado |
| --- | --- |
| Build da imagem a partir do repositório | Aprovado |
| Healthcheck do contêiner | Aprovado |
| Instalação começa sem proprietário | Aprovado |
| Acesso anônimo a dados recebe HTTP 401 | Aprovado |
| Onboarding e sessão local | Aprovado |
| Criação e listagem de tarefa | Aprovado |
| Priorização em Hoje | Aprovado |
| Busca por tarefa | Aprovado |
| Exportação ZIP e teste de integridade | Aprovado |
| Dados preservados após reinício | Aprovado |
| Remoção dos dados fictícios e retorno ao estado vazio | Aprovado |
| Ocupação do disco após o teste | 68% |

## Procedimento resumido

1. Clonar o repositório em um diretório novo.
2. Copiar `.env.example` para `.env`.
3. Executar `docker compose up -d --build`.
4. Aguardar o estado `healthy` e consultar `/health` e `/api/status`.
5. Confirmar HTTP 401 em `/api/me` sem sessão.
6. Concluir o onboarding com dados descartáveis.
7. Criar uma tarefa e verificar Hoje, Busca e exportação.
8. Reiniciar o serviço e confirmar a permanência da tarefa.
9. Remover somente o volume descartável do piloto e subir novamente.
10. Confirmar `configured: false` na nova instalação vazia.

Este ensaio valida o aceite instalável do M1. Ele não valida ainda o harness de IA, restauração em outra máquina, atualização automática, uso concorrente ou segurança para exposição direta à internet.

## Segunda rodada — macOS independente e M2 inicial

Em 11/10/2026, clone novo em macOS ARM64, Python 3.12.13, ambiente virtual e dados isolados. Instaladas as dependências de `requirements.lock`, sem depender do primeiro host Ubuntu.

- 17 testes automatizados passaram em Linux de desenvolvimento e no Mac.
- Chromium headless executou onboarding → tarefa → área → busca → IA desativada → prévia de contexto → viewport móvel de 390 px → concluir tarefa → sair/entrar, sem erro JavaScript.
- Outro fluxo Chromium usou o adaptador HTTP real contra um servidor de respostas simuladas: proposta sem gravação → recarregar → confirmar → tarefa única → nova proposta → recusar. A chamada não saiu da máquina de teste.
- Testes cobrem concorrência, aprovação idempotente, área não autorizada, ferramenta desconhecida, resposta malformada, falha do provedor, cota diária, consentimento e execução interrompida sem repetição automática.
- Correções motivadas por evidência: formulário perdia referência após `await`, tentativa de login sofria rollback, logout escondido no mobile, comparação de data UTC e busca com resposta atrasada.

Não foram validados qualidade com modelo real, custo monetário, benchmark de economia, restauração em segunda máquina ou experiência sem ajuda com usuários. A instalação independente não equivale a teste de restauração. Há um aviso de depreciação não bloqueante no TestClient/AnyIO.

## Terceira rodada — M2, M3 e recuperação

Versão `0.2.0a1`, 11/10/2026: 31 testes aprovados em Linux e macOS. Incluem reserva/reconciliação, uso desconhecido, excesso, leitura atômica de destino/chave, validação sem segredo, ZIP malicioso, entrada parcialmente inválida, deduplicação, exclusão compartilhada, escopo por área, papéis de conversa e onboarding persistido.

Chromium a 390 × 844 px: cadastro → objetivo → upload → prévia → seleção → confirmação → reload → salvar IA desativada → busca → fonte original → excluir lote. Sem erro JavaScript ou transbordamento horizontal. Fluxo separado de proposta/confirmar/recusar passou com adaptador HTTP e provedor simulado.

Snapshot sintético com proprietário, tarefa e fonte foi criado no Linux, transferido e restaurado no Mac. Login, tarefa e fonte conferidos; sessões invalidadas. Sem exportação real de usuário ou chamada paga.

Não fecha aceite de qualidade de IA, cobrança real ou compatibilidade ampla dos exports. Sem benchmark de economia ou piloto externo concluído.

## Quarta rodada — revisão de versões e pausa de fontes

Versão `0.2.0a2`, 11/10/2026: 33 testes passaram em Linux e macOS. Cobrem notas de mesmo caminho/conteúdo diferente na mesma área, duplicatas com estado pausado preservado, pausa fora da busca e de novos contextos, reativação, exportação, persistência após reinício e migração de banco existente com fontes ativas por padrão. Autenticação e origem inválida bloqueiam alteração de estado.

Chromium a 390 × 844 px percorreu o onboarding anterior e acrescentou reimportação alterada → aviso de conflito → abrir original → cancelar lote → pausar → verificar busca vazia → reload → reativar → verificar busca → excluir. Sem erros JavaScript. Dados sintéticos; nenhuma chamada paga ou coleta de histórico de usuário. A seleção de versão é manual e não resolve equivalência semântica ou renomeações.

## Quinta rodada — organização assistida

Versão `0.2.0a3`, 11/10/2026: 40 testes aprovados. Novos casos cobrem prévia limitada, fontes fora da seleção/área, saída com IDs inventados, orçamento compartilhado, seleção parcial, nomes existentes, confirmação concorrente/idempotente, recusa, exportação e bloqueio de propostas com fontes pausadas, excluídas ou movidas. Nenhuma área é criada antes da confirmação. Um replay do pedido após aplicação retorna a mesma execução mesmo que as fontes tenham mudado de área.

No Chromium mobile, o adaptador HTTP real falou com um provedor simulado local: importação → seleção → prévia → consentimento → sugestão → reload → edição do nome → conferir original → confirmar → verificar área/destino das fontes → editar descrição da área → conferir novo contexto. Nenhuma tarefa adicional foi criada. Fluxo anterior de onboarding/importação e tarefa/recusa também passou. Sem erros JavaScript ou transbordamento horizontal na tela de revisão a 390 px.

Isso valida o contrato e a revisão humana, não qualidade semântica, cobrança real ou adequação das sugestões a usuários reais. A geração usa somente o início das fontes escolhidas e não implementa perfil pessoal inferido.

## Sexta rodada — contexto pessoal e objetivo revisáveis

Versão `0.2.0a4`, concluída em 12/10/2026: 48 testes passaram no Linux e macOS. Casos novos cobrem trechos de apoio inexistentes, fontes externas, campos inesperados, confirmação parcial/concorrente, conflito com edição mais recente, fonte pausada, recusa, orçamento compartilhado, contexto fora do envio padrão e inclusão explícita. Backup/restauração também preservam contexto confirmado e revisão. Propostas originais e escolhas aplicadas permanecem na exportação.

Chromium mobile (390 × 844): fontes → prévia → geração simulada → reload → edição de sugestão → abrir apoio → confirmar contexto/objetivo → objetivo em Hoje → prévia sem contexto pessoal → inclusão explícita → limpar contexto. Fluxos anteriores de organização, tarefas e onboarding/importação passaram. Corrigida a associação explícita de rótulos aos campos da tela nova. Nenhum erro JavaScript ou transbordamento horizontal na revisão.

Sem chamada paga ou histórico pessoal real. O teste verifica presença literal dos trechos e controles de aplicação, não se a interpretação do modelo é correta, atual ou atribuída à pessoa certa. Esses aceites dependem de modelos reais e usuários piloto.

## Recuperação e independência — 12/10/2026

Validação da rotina de backup: commit `23d3059cc1c68517ef9950e441a8b224bcc7c81b` passou no procedimento completo de Ubuntu 24.04.5 novo: 62 testes offline, atualização da 0.2.0a3 para a 0.2.0a7, reinício, restauração e HTTP/assets do pacote. Após isso, um caso adicional de disco sem espaço para gravar o próprio estado de erro foi corrigido; os 63 testes passaram no Mac e os quatro testes específicos de backup automático passaram no Linux. O procedimento Ubuntu completo não foi repetido para essa correção pontual; ela mantém a falha em memória e log quando persistir é impossível. Contêineres e dados sintéticos do ensaio foram removidos.

0.2.0a7: 62 testes aprovados no Linux. Casos novos: APIs de backup autenticadas/com proteção de origem, download restaurável, limite de retenção, arquivo não gerenciado preservado, intervalo de 24 horas, tentativa após falha, erro visível, preservação de snapshots anteriores e rotina retomada ao iniciar sem duplicação imediata. Fluxos Chromium mobile no Mac aprovados: habilitar/desabilitar política, criar/baixar SQLite, sem transbordamento; onboarding, acesso, importação e harness anteriores também passaram. Agendamento testado com relógio controlado e reinício real do lifespan; não houve espera de 24 horas nem falha elétrica real.

Validação Ubuntu concluída: `scripts/clean_ubuntu.sh` executado integralmente sobre o commit público `a97a22b388bd251961118475ca8d6646925acbac`. Contêiner Ubuntu 24.04.5 LTS, Python 3.12.3, ambiente virtual/dependências e instalação do pacote novos. Após instalar, a rede do contêiner foi desconectada. Passaram 59 testes, migração 0.2.0a3 → 0.2.0a6, reinício, restauração em diretório separado para a versão antiga e inicialização HTTP do pacote instalado com todos os módulos da interface. O script terminou com código 0 e removeu seu contêiner/diretório temporário. Não valida boot/systemd de uma VM completa, acesso remoto público, modelo real ou instalação por pessoa sem ajuda.

A primeira preparação manual encontrou uma limitação do ambiente: o empacotador não grava metadados em código montado somente leitura. O procedimento definitivo copia o código para um diretório de build gravável; nenhuma alteração no produto foi necessária. Os testes executam o pacote instalado fora do diretório-fonte. Houve aviso de depreciação de `BlockingPortal` da dependência de testes, sem falha.

Revisão automatizada do histórico local anterior a esta rodada: 18 commits, 178 blobs únicos; nenhuma ocorrência dos padrões procurados de host/caminho privado, chave privada ou formatos selecionados de token. Não é auditoria completa nem garantia de ausência de qualquer segredo. Não houve importação de dados reais nem chamada paga.

Ensaio M4 adicional: `scripts/upgrade_smoke.py` passou no Linux e macOS, usando snapshots Git isolados de 0.2.0a3 → 0.2.0a6. Criou dados sintéticos na versão antiga, gerou snapshot, migrou, reiniciou e restaurou o snapshot em diretório separado para a versão antiga. Preservou identidade, tarefa, fonte e objetivo; o contexto novo persistiu após reinício. Sessão antiga recusada após restauração; execução interrompida marcada como falha, sem duplicação e com reserva conservada. Não usou instalação/dados reais nem chamadas de IA. Não é ensaio de sistema operacional recém-instalado ou reinstalação de dependências.

0.2.0a6: 59 testes passaram no Linux. Novos casos verificam autenticação/origem, persistência privada e rejeição de endereços inadequados no assistente de acesso. Chromium mobile no Mac passou: salvar preferência/endereço, reabrir, verificar sessão atual e ausência de transbordamento. A rede do host não foi alterada; acesso externo sem Tailscale não foi testado. Procedimento manual de atualização/recuperação documentado no M4; automação e ensaio em Ubuntu limpo pendentes.

Na 0.2.0a5, 52 testes passaram no Linux e o fluxo Chromium mobile passou no Mac: escolher conexão direta, trocar para servidor local, verificar limpeza de chave/modelo, salvar, recarregar e desativar. Sem transbordamento horizontal. Nenhuma chamada ao endpoint configurado foi necessária. Sintaxe dos módulos JavaScript validada. O endereço OpenAI segue a [referência oficial](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create); a seleção não certifica compatibilidade de um modelo nem cobra um teste de geração.

52 testes automatizados aprovados no Linux após reforço do backup: verificação somente leitura, rejeição de referências inválidas, preservação de arquivos existentes e limpeza de uma restauração cuja publicação falhou. O ensaio existente continua verificando login, fontes, tarefas, objetivo e contexto após restaurar. Nenhum dado pessoal ou modelo pago utilizado. O roadmap recebeu critérios explícitos de configuração interna sem dependência de Tailscale/OpenRouter; acesso remoto guiado permanece planejado, não validado.
