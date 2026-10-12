# Validação do M1

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

0.2.0a6: 59 testes passaram no Linux. Novos casos verificam autenticação/origem, persistência privada e rejeição de endereços inadequados no assistente de acesso. Chromium mobile no Mac passou: salvar preferência/endereço, reabrir, verificar sessão atual e ausência de transbordamento. A rede do host não foi alterada; acesso externo sem Tailscale não foi testado. Procedimento manual de atualização/recuperação documentado no M4; automação e ensaio em Ubuntu limpo pendentes.

Na 0.2.0a5, 52 testes passaram no Linux e o fluxo Chromium mobile passou no Mac: escolher conexão direta, trocar para servidor local, verificar limpeza de chave/modelo, salvar, recarregar e desativar. Sem transbordamento horizontal. Nenhuma chamada ao endpoint configurado foi necessária. Sintaxe dos módulos JavaScript validada. O endereço OpenAI segue a [referência oficial](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create); a seleção não certifica compatibilidade de um modelo nem cobra um teste de geração.

52 testes automatizados aprovados no Linux após reforço do backup: verificação somente leitura, rejeição de referências inválidas, preservação de arquivos existentes e limpeza de uma restauração cuja publicação falhou. O ensaio existente continua verificando login, fontes, tarefas, objetivo e contexto após restaurar. Nenhum dado pessoal ou modelo pago utilizado. O roadmap recebeu critérios explícitos de configuração interna sem dependência de Tailscale/OpenRouter; acesso remoto guiado permanece planejado, não validado.
