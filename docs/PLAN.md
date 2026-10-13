# Mia — plano de produto e execução
Versão 0.15 · 12/10/2026 · Status: 0.2.0a11 acrescenta operação nativa, atualização consciente e recuperação durável, revisão de tarefas e planos HTTPS. Ensaios técnicos Linux/Ubuntu isolado e navegador passaram; licença, provedor direto, acesso remoto real e participantes continuam pendentes. Situação consolidada em RELEASE-CHECKLIST.md.

## 1. Produto
Mia é um harness de IA pessoal acessado pelo navegador, com contexto, memória, ferramentas, permissões, execução persistente e controle de custos.

Proposta: **IA pessoal com contexto, ferramentas e controle de custos.**
A central de comando é a interface do harness.

Decisões confirmadas:
- Código aberto, com licença específica pendente de revisão das dependências.
- Ubuntu primeiro, em servidor ou computador pessoal.
- Primeira versão com poucos usuários piloto.
- Onboarding personalizado.
- IA local ou APIs externas escolhidas pelo usuário.
- Sem conta central, infraestrutura do fundador ou plataforma comercial obrigatória.
- Configuração de IA e acesso pela própria Mia. Tailscale e OpenRouter não são dependências obrigatórias; seu uso no ambiente de teste não define a instalação do produto.
- Repositório totalmente novo, histórico Git iniciado do zero e README independente.
- Nenhum histórico pessoal, conversa, vault, credencial ou configuração privada no produto.
- mia.cc é o domínio proposto; disponibilidade e propriedade ainda não verificadas.

“Vender” descreve a proposta de valor; preço, modelo de receita e serviços comerciais ainda não foram definidos.

## 2. Repositório independente
O desenvolvimento passa a acontecer em um repositório novo, sem fork, clone espelhado, branches antigas, tags antigas ou commits do sistema de origem.

A experiência existente pode orientar o produto. Componentes de software podem ser extraídos seletivamente após revisão de licença, portabilidade, dependências e conteúdo.

Procedimento:
1. Iniciar diretório e Git novos.
2. Escrever README, plano e contratos próprios.
3. Selecionar código reutilizável por lista explícita.
4. Generalizar nomes, caminhos, regras, prompts e fontes.
5. Revisar cada arquivo antes do primeiro commit que o incluir.
6. Verificar documentos, testes, assets, configurações, metadados e histórico.
7. Publicar somente material aprovado para distribuição.

Excluir da distribuição:
- Vaults, notas, conversas, memória, decisões pessoais e listas de contatos.
- Dados de clientes, CRM, campanhas e resultados privados.
- Tokens, chaves, URLs privadas, identificadores de contas e caminhos do fundador.
- Configuração SSH, gitconfig, arquivos de ambiente e backups.
- Exemplos, capturas ou fixtures derivados de pessoas e negócios reais.
- Histórico, documentação de operação e planos do projeto de origem.

A revisão deve preservar avisos legais exigidos por bibliotecas reutilizadas; remover dados pessoais não significa remover atribuições obrigatórias.

A instalação nasce vazia. Importação de dados é uma ação explícita do usuário depois de instalar.
O sistema de origem permanece separado: esta extração não apaga seus dados nem reescreve seu histórico.

## 3. Valor para o usuário
- Evitar repetir contexto em cada conversa.
- Recuperar informações autorizadas com evidências.
- Usar modelos adequados ao trabalho e ao orçamento.
- Fazer a IA operar ferramentas dentro de limites claros.
- Revisar alterações antes da execução.
- Retomar tarefas e conversas após reinício.
- Manter dados exportáveis e escolher onde executar.

Exemplo: preparar uma reunião com arquivos selecionados, mostrar fontes, sugerir ações e registrar apenas as aprovadas.

## 4. Núcleo do harness
| Componente | Responsabilidade |
| --- | --- |
| Contexto | Recuperar somente informação relevante e autorizada |
| Memória | Persistir informações revisáveis e rastreáveis |
| Modelos | Adaptar execução local e provedores externos |
| Ferramentas | Validar parâmetros, permissões, efeitos e resultados |
| Políticas | Controlar aprovação, orçamento e condições de parada |
| Execuções | Persistir estado, permitir retomada e evitar efeitos duplicados |
| Auditoria | Registrar fontes, uso, decisões, ações e falhas |
| Interface | Expor conversa, configuração e central de comando |

O contrato do harness define entrada, ciclo, estados e critérios de aceite. Uma mudança de modelo não deve alterar a identidade, as permissões ou as fontes de verdade.

## 5. Arquitetura proposta
- Frontend web portátil, usando componentes generalizados de uma base existente quando viável.
- API própria para autenticação, contexto, ferramentas e execução.
- Conteúdo local em formato aberto.
- Banco local para configuração, sessões, execuções e orçamento; SQLite é a hipótese inicial.
- Índices derivados e reconstruíveis.
- Adaptadores opcionais de IA, fontes e conectores.
- Pacote Ubuntu para web e API, com caminhos e usuário de execução configuráveis.
- Uma instalação por proprietário no piloto.
- Isolamento por usuário previsto no modelo; hospedagem compartilhada e colaboração ficam para etapa posterior.

Decisões técnicas finais dependem de testes de concorrência, restauração e build independente.
Nenhuma biblioteca será escolhida por exigir uma plataforma comercial como caminho obrigatório.

## 6. Onboarding
Implementado: acesso, objetivo declarado, importação revisável, configuração gráfica de IA e caminho à primeira consulta/Hoje. Fluxo retomável, sugestões de áreas e contexto pessoal/objetivo com evidências e confirmação. Detalhes em [ONBOARDING.md](ONBOARDING.md).

1. Criar acesso local e configurar idioma e fuso.
2. Informar objetivos e tipos de trabalho.
3. Criar áreas e prioridades.
4. Começar vazio ou importar fontes autorizadas.
5. Escolher IA local, API externa própria ou modo sem IA.
6. Definir orçamento e nível de autonomia.
7. Revisar configuração e concluir a primeira tarefa real.

O fluxo funciona sem geração por IA. Pode ser retomado e editado.
Não criar objetivos, contatos, números ou tarefas fictícias.
Não bloquear o primeiro uso por falta de um conector externo.

Após o primeiro teste do proprietário, o M3 foi detalhado com Markdown/texto/ZIP, prévia, seleção, relatório e fontes recuperáveis. A execução mantém a sequência M2 → M3 conforme orientação do proprietário. Não confundir instalação vazia com experiência sem contexto: o usuário traz o próprio conhecimento durante o onboarding.

## 7. Baixo custo como requisito verificável
Estratégias:
- Usar regras determinísticas quando geração não agrega valor.
- Recuperar contexto seletivamente.
- Aplicar cache somente quando seguro, autorizado e válido.
- Resumir históricos com rastreabilidade.
- Selecionar modelo por capacidade, qualidade necessária e orçamento.
- Permitir modelos locais.
- Limitar contexto, saída, duração, passos e novas tentativas.
- Reservar orçamento antes da chamada e reconciliar o uso real depois.
- Pausar ao atingir limites; não escalar custo silenciosamente.
- Registrar tokens, modelo, ferramenta e uso.
- Distinguir custo estimado, confirmado e desconhecido.

Avaliação:
- Definir tarefas representativas e critérios de qualidade antes do teste.
- Comparar custo, latência, tokens e sucesso com uma abordagem que envia todo o contexto.
- Verificar se redução de custo preserva resposta correta e ação segura.
- Medir nas máquinas piloto, sem publicar resultados pessoais.
- Só estabelecer promessa de preço/desempenho depois das medições.

IA local tem custos de equipamento, energia e operação.
APIs seguem condições e preços do provedor escolhido.
Assinatura de aplicativo de chat não é crédito de API.
Não há promessa de gasto mensal fixo ou economia percentual nesta versão.

## 8. Experiência web
Navegação proposta: Hoje, Áreas, Planejamento, Inteligência e Sistema; Busca transversal.

- Hoje destaca prioridades, compromissos e mudanças relevantes.
- Áreas são configuradas pelo usuário.
- Planejamento reúne objetivos, semana, projetos e decisões.
- Inteligência apresenta conversa, fontes, propostas e custo.
- Sistema reúne modelos, fontes, permissões, orçamento, backup e saúde.
- Origem, idade do dado, inferência e lacuna são distinguíveis.
- Ausência de dado não vira zero.
- Inventário técnico fica fora do fluxo principal.

## 9. Execução por marcos
| Marco | Entrega | Aceite |
| --- | --- | --- |
| M0 — Fundação limpa | Repositório novo, README, plano, contratos e revisão de extração | Um histórico independente sem conteúdo privado; capacidades planejadas claramente identificadas |
| M1 — Núcleo instalável | Web, API, acesso local, conteúdo, tarefa, busca e persistência | Ubuntu limpo funciona sem conta externa; reinício preserva dados |
| M2 — Harness mínimo | Contexto, adaptador de modelo, ferramentas, propostas, confirmação, uso e limites | Consulta com fontes e ação confirmada sem duplicação, respeitando orçamento |
| M3 — Onboarding e personalização | Fluxo retomável, objetivo, configuração gráfica, primeira consulta, exportações de conversas e sugestões revisáveis | Usuário chega ao primeiro resultado com conhecimento próprio, sem cadastro manual extensivo |
| M4 — Operação confiável | Retomada, isolamento, atualização, recuperação e backup | Execução interrompida retoma sem repetir efeitos; restauração em segunda máquina |
| M5 — Pilotos e release | Testes reais, benchmark de custo, licença, documentação e pacote | Usuários instalam e operam sem intervenção do fundador; alegações sustentadas por resultados |

Branches de implementação partem da linha do novo repositório. O produto existente não recebe mudanças para acomodar o Mia.

## 10. Testes obrigatórios

### Complemento aprovado em 12/10: configuração autônoma

Manter os marcos, acrescentando estes critérios:

- **M3 — IA na interface:** escolher serviço direto, gateway opcional ou servidor local, informar credencial/modelo/limites e conferir destino. Seleção guiada inicial implementada na 0.2.0a5: sem IA, OpenAI direto com endereço preenchido, serviço compatível ou servidor local com instruções. Na 0.2.0a10, verificação explícita consulta o catálogo `/models` do destino salvo, sem geração ou envio de notas. Informa acesso, presença exata do identificador ou inconclusão; não comprova chave, saldo, ferramentas ou qualidade. Seleção em catálogo e outros adaptadores nativos ainda pendentes. Nenhum gateway será intermediário obrigatório. Verificar conexão sem geração quando possível; teste que gere custo exige valor limite e confirmação explícitos.
- **M4 — Acesso na interface:** mostrar acesso neste computador, na rede local e remoto; guiar endereço/domínio, HTTPS e diagnóstico. Acesso local e LAN não exigem VPN nem conta externa. Não publicar portas automaticamente. Configuração remota deve apresentar alterações e obter confirmação antes de aplicá-las, com opção de desativar e recuperar acesso local.
- **M4 — Limites da rede:** quando a rede não aceitar conexões de entrada, explicar a necessidade de uma rota alcançável (configuração do roteador/IPv6, servidor próprio ou túnel opcional escolhido pelo usuário). A interface não pode prometer resolver CGNAT sem infraestrutura adicional. Nenhum fornecedor de túnel será obrigatório.
- **M5 — Aceite independente:** instalar e concluir uma consulta com provedor direto, sem OpenRouter; acessar de outro dispositivo sem Tailscale; validar HTTPS remoto em instalação controlada pelo participante. Documentar o que ainda exigiu ação fora da Mia.

Hoje: configuração de API compatível já acontece em Sistema. Na 0.2.0a6, o assistente de acesso salva preferências e endereço HTTPS e diagnostica a sessão atual; não aplica configuração de rede/certificados nem valida acesso externo. Detalhes em [ACCESS.md](ACCESS.md). O link do piloto continua usando Tailscale até existir e ser validada uma alternativa. Não alterar a rede do piloto apenas para demonstrar independência.

Retorno ao plano original após esse complemento: concluir aceites M2/M3 com modelo real e fontes próprias dos participantes (modelo via gateway e teto total de US$ 1 já autorizados; fontes reais dos participantes pendentes); seguir no M4 com recuperação e atualização reproduzível; somente então fechar M5. Não marcar marcos concluídos pela existência dos assistentes. A automação de HTTPS/rede e validação sem Tailscale continuam pendentes no M4/M5.

### Verificações do produto
- Instalação e reinício em Ubuntu limpo.
- Persistência ao recriar serviços.
- Núcleo sem internet e sem IA, após instalação.
- Consulta com motor local sem depender de gateway externo.
- Fontes e dados isolados por identidade.
- Autorização no backend para cada ferramenta.
- Dados recuperados não ampliam permissões.
- Alteração sem confirmação rejeitada no servidor.
- Chamadas repetidas não repetem efeitos.
- Orçamento respeitado com execuções concorrentes.
- Loops e falhas repetidas param dentro dos limites.
- Falha de conector afeta só o recurso relacionado.
- Restauração em segunda máquina.
- Verificação de dados privados e segredos no conteúdo e em todos os commits antes da publicação.
- Fluxo no navegador: onboarding → contexto → resposta → proposta → confirmação → persistência → uso/custo.

## 11. Domínio e distribuição
mia.cc poderá apresentar o produto e oferecer documentação e downloads.
As instalações privadas não dependem desse domínio.
Aquisição do domínio, identidade visual, preços e hospedagem opcional serão tratados separadamente.

## 12. Estado desta entrega

Atualização 0.2.0a11: [operação nativa](OPERATIONS.md) para instalações novas, com preparação de versão em venv separado, snapshot privado antes de trocar, saúde/versão por HTTP, bloqueio de alterações durante operação pendente e recuperação repetível em dados novos. O retorno exige ciência de que mudanças posteriores ficam preservadas em separado. Modo manual/Docker continua suportado; bootstrap gerenciado não se atualiza a si próprio. Revisão independente corrigiu corridas de startup, identidade de processo/release, precedência do ambiente, recuperação repetida e aliases por symlink. Testes adversariais incluem SIGKILL e falha fechada com snapshot/banco ausente.

Sistema mostra estado operacional e prepara plano explícito para proxy HTTPS opcional, sem executar comandos de rede. Caddyfile gerado passou em ensaio loopback com TLS verificado, origem, cookie Secure e recuperação local; isso não comprova rota pública/LAN em outro dispositivo. Propostas de tarefa agora permitem edição antes de aprovação, preservando original e resultado aplicado no histórico/exportação e após restauração.

A distribuição preserva 279 textos de avisos de terceiros, com inventários Python/Rust e checksums; roda verificação de wheel/sdist e pacote instalado. Essa revisão tem escopo documentado em [DEPENDENCIES.md](DEPENDENCIES.md), sem conceder licença própria ou certificar todos os binários/OS upstream. [Opções de licença](LICENSE-OPTIONS.md), roteiro independente e template privado de piloto foram preparados. Não foram criados participantes, fontes reais ou resultados externos. Nenhuma nova chamada paga: acumulado conhecido permanece US$ 0.0045882598 sobre teto total US$ 1.

Os aceites externos não foram apagados: M0 ainda depende da licença; M2 de provedor direto/qualidade representativa; M3 de fontes/exports autorizados e uso por participantes; M4 de boot nos sistemas suportados, cópia externa e rota HTTPS real; M5 de 2–3 participantes, benchmark representativo e decisão de release. A existência do gerenciador e dos planos não fecha esses marcos.

Atualização de 12/10 — 0.2.0a9: 17 chamadas sintéticas de DeepSeek via OpenRouter, custo informado acumulado US$ 0.0045882598 sobre teto total US$ 1. Organização e personalização passaram com edição, aprovação parcial e idempotência. Comparação de contexto revelou falha de ordenação da busca, corrigida e revalidada. Entrada caiu de 2.653 para 983 tokens no caso medido; custo observado não diminuiu. Detalhes em [REAL-MODEL-VALIDATION.md](REAL-MODEL-VALIDATION.md). Provedor direto, fontes/exports reais e pilotos externos continuam pendentes. Os itens abaixo registram a evolução histórica, inclusive pendências posteriormente resolvidas.
- Fundação documental preparada em repositório Git local novo.
- README independente e contrato inicial do harness.
- Nenhum código ou histórico do sistema de origem importado.
- M1 implementado: onboarding, autenticação local, áreas, tarefas, Hoje, Busca, exportação e persistência SQLite.
- Testes automatizados do fluxo local, autenticação, origem, exportação, instalação vazia e reinício.
- Dockerfile, Compose e documentação Ubuntu validados em um host piloto: imagem construída do zero, serviço saudável, acesso anônimo negado, onboarding, login, tarefas, Hoje, Busca e exportação exercitados.
- Persistência confirmada após reiniciar o contêiner; os dados fictícios de validação foram removidos e a instância voltou ao estado inicial vazio.
- O teste manteve o host em 68% de ocupação de disco. Detalhes reproduzíveis estão em `docs/VALIDATION.md`.
- Conectores, restauração automática e expansão do harness continuam nos marcos seguintes.
- O proprietário tornou o repositório público; a licença aberta específica permanece pendente.
- M1 revisado no navegador em macOS independente: corrigidos formulários após envio, persistência do bloqueio de login, saída no celular, data no fuso do proprietário e resultados obsoletos na busca.
- M2 inicial implementado: contexto por área, adaptador opcional Chat Completions, proposta de tarefa, confirmação/recusa, histórico, cota de chamadas e idempotência transacional.
- 17 testes automatizados e dois fluxos reais de navegador aprovados. O fluxo de IA usa provedor simulado local, sem chamada paga.
- Faltam ao aceite M2: modelo real, avaliação da qualidade/citações, orçamento monetário e demais requisitos do contrato-alvo. Pedidos ainda são independentes, sem conversa contínua.
- O proprietário fez os primeiros testes pela interface no celular e apontou que o onboarding precisa trazer conhecimento próprio para produzir valor inicial. Não há ainda piloto concluído com usuários externos.
- Execução manteve os marcos originais. M2 ampliado com preços configuráveis, reserva estimada, reconciliação de uso, reserva conservada quando uso é desconhecido e bloqueio por excesso.
- M3 inicial: onboarding retomável, objetivo, upload/colagem, revisão, seleção, deduplicação, lotes, busca textual, fontes no contexto e configuração gráfica. Adaptadores de conversas são experimentais.
- M4 parcial: snapshot consistente, integridade, restauração em destino vazio e sessões invalidadas. Backup sintético Linux restaurado no Mac.
- M4 recuperação entre versões: ensaio reproduzível 0.2.0a3 → 0.2.0a6 → restauração para 0.2.0a3 passou em ambientes isolados no Linux e Mac. Preservou dados, migração, reinício, invalidação de sessão restaurada e reserva de chamada interrompida. Instalação/atualização automatizada em Ubuntu limpo, falha elétrica e recuperação sem ajuda continuam pendentes.
- Atualização de evidência M4: instalação de pacote/dependências em contêiner Ubuntu 24.04 novo concluída, seguida de 59 testes, atualização/restauração e HTTP/assets com rede desconectada. Procedimento reproduzível em `scripts/clean_ubuntu.sh`; detalhes e limites em VALIDATION.md. Isso fecha o ensaio técnico isolado, não boot de sistema completo, atualizador automático ou operação por usuário sem ajuda.
- M4 na 0.2.0a7: backup manual/download e política opcional de 24 horas pela interface; retenção de 1–30 snapshots próprios após nova cópia válida; estado de falha visível e nova tentativa após uma hora. A rotina depende da Mia em execução e de um único worker; não envia cópia para outra máquina. Restauração ainda por comando.
- 31 testes passaram no Linux e Mac; onboarding/importação/busca mobile e proposta/confirmar/recusar passaram no navegador. Dados reais do proprietário permanecem em sua instalação.
- M3 ampliado: revisão informa duplicatas e notas com mesmo caminho/conteúdo diferente; usuário compara fontes e pausa/reativa versões. Fontes pausadas permanecem exportáveis e ficam fora de novas consultas. Não há escolha automática de versão.
- M3 organização assistida: até seis fontes explícitas, prévia limitada, chamada com orçamento compartilhado, até quatro áreas sugeridas, edição/seleção/recusa, confirmação transacional e revalidação de fontes. Cria áreas e move fontes somente após aprovação, preservando proposta original e escolha aplicada. Áreas podem ser editadas depois.
- M3 personalização inicial: sugestões de contexto pessoal/objetivo com trechos literais de apoio, edição e confirmação parcial, controle de revisão e revalidação das fontes. Contexto confirmado editável e exportável; uso em Inteligência somente por opção explícita em cada consulta. Qualidade semântica não validada por testes simulados.
- Pendências: modelo real/cobrança, amostras reais autorizadas de exports dos usuários de teste, projetos estruturados, conversa contínua, múltiplos usuários/workers, atualização automática, cópia de backup fora da máquina e M5 externo.
- Validação com modelo real continua exigindo provedor/modelo e teto de gasto autorizados; isso não bloqueia importação e busca local. Piloto externo será revisado para usar fontes reais selecionadas conforme `PILOT.md`.

Este plano orienta o trabalho e não comprova funcionalidades, portabilidade, segurança ou economia já entregues.

