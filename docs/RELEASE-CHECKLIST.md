# Aceites de release — 13/10/2026

## Nova jornada na 0.2.0a12

Implementados: preparação por fontes sem área/chave obrigatória, uploads retomáveis, revisão por grupos, indexação progressiva, exports com proveniência, foco, trechos em Hoje, conversas persistentes e serviço de usuário/migração manual. [Evidência e limites](EXPERIENCE-VALIDATION.md) distinguem testes sintéticos, processo Linux e aceites nas máquinas reais.

O novo fluxo não tem o limite antigo de 300 entradas. Quotas e cobertura permanecem explícitas. Launcher/empacotador Mac são fundação técnica: assinatura/notarização, runtime/wheels Mac reais, instalação limpa, login/suspensão e boot real continuam abertos. Drive recorrente, sync offline, qualidade com fontes próprias e primeiro valor sem assistência não foram comprovados. Apache-2.0 aplicada aos arquivos próprios em 13/10; o [roadmap](ROADMAP.md) separa os aceites restantes.

## Revisão de experiência — 13/10/2026

No teste do proprietário da a11, o uso do zero recebeu **2/10**. Houve rejeição relatada de vault ZIP; aquela implementação bloqueava mais de 300 entradas antes de filtrar conteúdo útil. A instalação do Mac precisou de Terminal, correção de pip e orientação para reiniciar vazio. Isso confirma saúde/versionamento/instalação vazia naquele teste, não qualidade de migração ou uso sem ajuda.

O próximo ciclo segue [EXPERIENCE-PLAN.md](EXPERIENCE-PLAN.md). M3 precisa migração representativa/primeiro valor com fontes e Hoje útil; M4 precisa uso diário sem Terminal e aceites distintos para local e servidor; M5 exige participantes com sua preferência de instalação e fontes próprias. O proprietário escolheu servidor Linux e retomada de trabalho; isso não obriga novos participantes a hospedar em servidor. Mockups e 141 testes existentes não fecham esses aceites.

O replanejamento inicial não alterou o código; a implementação posterior a12 está descrita acima. Apache-2.0 foi adotada posteriormente; alegações de economia continuam pendentes. Evidências históricas permanecem abaixo.

Estado: **alpha técnica, não release final para distribuição ampla**. Esta lista descreve evidência, não promessa.

Atualização de evidência do modelo (0.2.0a9): consulta, ação, organização e personalização com modelo real via OpenRouter validadas em material sintético. Comparação de contexto executada e falha de busca corrigida. Total acumulado: 17 chamadas, US$ 0.0045882598 informado pelo provedor, dentro do teto total US$ 1. [Resultados e limitações](REAL-MODEL-VALIDATION.md). Não fecha provedor direto, economia, fontes reais ou piloto externo.

Ensaio histórico em Ubuntu 24.04.5 isolado aprovado: instalação nova, 59 testes sem rede, migração, reinício, restauração e HTTP/assets do pacote instalado. Na 0.2.0a10 foram 77 testes Linux/Mac. A 0.2.0a11 passou 141 testes no Linux e no Ubuntu 24.04 isolado, com instalação nova de pacote e validação offline. Evidência e limites em VALIDATION.md. Protocolo em [BENCHMARK.md](BENCHMARK.md), com ensaio sintético executado.

| Marco | Comprovado | Falta para fechar |
| --- | --- | --- |
| M0 | Repositório independente; instalação vazia; Apache-2.0, NOTICE e avisos Python/Rust preservados e conferidos nos pacotes | Revisão da distribuição concreta de binários/OS conforme escopo em DEPENDENCIES.md |
| M1 | Instalação de pacote em Ubuntu 24.04 isolado e macOS; HTTP/assets, identidade, fontes, tarefas, busca e persistência | Instalação por participantes sem ajuda no M5 |
| M2 | Fontes delimitadas, ferramentas autorizadas, confirmação/idempotência, quotas/reserva/reconciliação; testes com simulador e modelo real via gateway, citações e custo observado | Provedor direto; qualidade representativa com participantes |
| M3 | Onboarding mobile, imports sintéticos, conflitos, organização/contexto revisáveis, configuração guiada de IA; organização e contexto aprovados com modelo real e fontes sintéticas | Exports reais escolhidos pelos participantes; primeiro resultado útil e compreensão da revisão |
| M4 | Snapshot/rotina local/retorno, restauração sintética entre máquinas; gerenciador nativo com update explícito, rollback/recuperação duráveis e testes de falha; planos HTTPS e proxy loopback com TLS/origem/cookie/recuperação verificados; Ubuntu offline | Ativação/boot systemd e launchd nas máquinas-alvo; configuração e prova da rota externa/LAN; cópia fora da máquina; bootstrap não se atualiza; um proprietário e um worker |
| M5 | Roteiro de 2–3 participantes, template privado de resultados, critérios de parada, Apache-2.0, avisos e verificações de distribuição | Participantes/fontes próprias, artefato preparado, benchmark representativo e decisão de release |

## Entradas necessárias para os aceites externos

A 0.2.0a11 fecha a implementação e os ensaios técnicos acima, sem declarar M0–M5 completos. O procedimento nativo está em [OPERATIONS.md](OPERATIONS.md); [ACCESS.md](ACCESS.md) distingue plano, infraestrutura e prova de acesso. A restauração automática na falha retorna erro explícito de atualização e preserva a tentativa; não oculta uma falha como sucesso.

- Para aceite sem gateway: provedor direto escolhido e credencial própria configurada na Mia. O ensaio atual via gateway já tem autorização total de US$ 1; não exige nova autorização dentro desse teto. Credenciais nunca entram no repositório.
- Participantes com suas próprias fontes e instalações. Sem necessidade de histórico do desenvolvedor; não enviar convites automaticamente.
- Apache-2.0 escolhida por delegação do titular; preservar LICENSE/NOTICE e obrigações dos componentes do artefato distribuído.
- Para validar acesso remoto sem Tailscale: destino/domínio controlado pelo instalador e rota de entrada disponível, ou alternativa opcional escolhida. O assistente atual não provisiona essa infraestrutura.

## Critério de parada do piloto

Não divulgar economia percentual, custo fixo, compatibilidade universal de modelos/exports, instalação sem ajuda ou segurança certificada a partir de testes simulados. Falha que perde dados, duplica efeitos, envia contexto não autorizado ou excede limites bloqueia release até correção e novo ensaio do caso.

Conversa contínua foi implementada na a12; projetos estruturados e conectores adicionais permanecem evolução de produto. Passar fluxos sintéticos não encerra os gates com participantes.

## Configuração na 0.2.0a10

Verificação do catálogo do destino salvo disponível na interface, sem gerar texto ou enviar notas. Autenticação e origem obrigatórias; destino comparado com a tela, sem redirecionamento de chave, resposta limitada a 2 MiB e prazo total de dez segundos. Falhas não exibem resposta bruta/segredos nem repetem a chamada. Catálogo público não comprova chave; alias ausente não comprova modelo inválido. Provedor direto real continua pendente.

Validação 0.2.0a10: 77 testes aprovados no Linux e Mac; onboarding mobile completo passou no Mac com servidor de catálogo local sintético. O teste verificou que salvar não consulta o catálogo, editar bloqueia a verificação até salvar, o botão faz apenas GET /models e nenhuma execução de geração é criada. Não foi feita nova chamada paga.
