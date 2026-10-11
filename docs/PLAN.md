# Mia — plano de produto e execução
Versão 0.5 · 11/10/2026 · Status: M1 validado tecnicamente em Ubuntu e macOS; M2 inicial testado com provedor simulado, ainda sem aceite com modelo real ou usuários.

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
| M3 — Personalização | Onboarding, áreas, configurações e importação explícita | Usuário novo conclui fluxo sozinho; instalação vazia não depende do sistema de origem |
| M4 — Operação confiável | Retomada, isolamento, atualização, recuperação e backup | Execução interrompida retoma sem repetir efeitos; restauração em segunda máquina |
| M5 — Pilotos e release | Testes reais, benchmark de custo, licença, documentação e pacote | Usuários instalam e operam sem intervenção do fundador; alegações sustentadas por resultados |

Branches de implementação partem da linha do novo repositório. O produto existente não recebe mudanças para acomodar o Mia.

## 10. Testes obrigatórios
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
- Fundação documental preparada em repositório Git local novo.
- README independente e contrato inicial do harness.
- Nenhum código ou histórico do sistema de origem importado.
- M1 implementado: onboarding, autenticação local, áreas, tarefas, Hoje, Busca, exportação e persistência SQLite.
- Testes automatizados do fluxo local, autenticação, origem, exportação, instalação vazia e reinício.
- Dockerfile, Compose e documentação Ubuntu validados em um host piloto: imagem construída do zero, serviço saudável, acesso anônimo negado, onboarding, login, tarefas, Hoje, Busca e exportação exercitados.
- Persistência confirmada após reiniciar o contêiner; os dados fictícios de validação foram removidos e a instância voltou ao estado inicial vazio.
- O teste manteve o host em 68% de ocupação de disco. Detalhes reproduzíveis estão em `docs/VALIDATION.md`.
- IA, conectores, restauração automática e o harness de execução continuam nos marcos seguintes.
- O código está em um repositório GitHub novo e privado enquanto a licença aberta é definida.
- M1 revisado no navegador em macOS independente: corrigidos formulários após envio, persistência do bloqueio de login, saída no celular, data no fuso do proprietário e resultados obsoletos na busca.
- M2 inicial implementado: contexto por área, adaptador opcional Chat Completions, proposta de tarefa, confirmação/recusa, histórico, cota de chamadas e idempotência transacional.
- 17 testes automatizados e dois fluxos reais de navegador aprovados. O fluxo de IA usa provedor simulado local, sem chamada paga.
- Faltam ao aceite M2: modelo real, avaliação da qualidade/citações, orçamento monetário e demais requisitos do contrato-alvo. Pedidos ainda são independentes, sem conversa contínua.
- Próxima decisão necessária: provedor/modelo de teste e teto de gasto autorizado. Depois, piloto com 2 a 3 pessoas conforme `PILOT.md`.

Este plano orienta o trabalho e não comprova funcionalidades, portabilidade, segurança ou economia já entregues.

