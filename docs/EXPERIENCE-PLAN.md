# Mia — migração de contexto e primeiro valor

13/10/2026 · Replanejamento de produto. **Proposta, não implementação.** Mantém os contratos de identidade, proveniência, aprovação e orçamento existentes. Não muda a instalação pessoal, limites de importação ou interface da 0.2.0a11.

## Decisões e evidência

O proprietário avaliou a experiência do zero em **2/10**. Relatou um vault ZIP recusado ao exceder 300 e dificuldade para entender instalação/configuração e manter o serviço no Mac. Isso é uma avaliação de uso real, não um benchmark nem um piloto com participantes externos. O arquivo não foi recebido; tamanho, contagem de notas e formatos internos permanecem desconhecidos.

Escolhas explícitas para o próximo piloto:

- **Resultado inicial:** retomar o trabalho, reconhecendo projetos, últimas decisões e pendências com fontes.
- **Referência do teste do proprietário:** servidor Linux sempre disponível, acessado pelo Mac e iPhone. Novos participantes escolhem instalação local ou servidor; a escolha do proprietário não se torna requisito para eles.
- **Objetivo de produto:** contexto próprio portátil e continuidade de trabalho, com custos visíveis. Substituição de assinaturas e economia permanecem hipóteses a medir, não promessas.

A 0.2.0a11 oferece base técnica, mas ainda não oferece migração representativa ou instalação para leigos. Os 141 testes comprovam comportamentos específicos; não contradizem a avaliação de experiência.

| Fricção confirmada no código | Consequência | Mudança proposta |
| --- | --- | --- |
| ZIP limitado a 300 entradas antes de filtrar pastas/metadados/mídia | Um vault pode ser recusado antes de contar notas úteis | Inventário e quotas distintas para arquivo, recursos e conteúdo elegível |
| Upload de 8 MiB, expansão de 20 MiB, parsing síncrono em memória/base64 | Migração grande não progride nem retoma | Transferência limitada por recursos, jobs duráveis e retomada |
| Área obrigatória antes de importar; seleção individual | Pessoa organiza manualmente antes de conhecer a Mia | Importar por origem/pasta/conversa, com revisão agrupada |
| Organização/personalização usa seis fontes e trechos iniciais | Não organiza nem compreende um vault inteiro | Recuperação por trechos e síntese progressiva de grupos, quando autorizada |
| Recuperação lexical de três trechos de 1.200 caracteres, dentro de uma área | Arquivo armazenado pode não produzir uma resposta útil | Melhorar índice, recorte, diversidade e escopo autorizado, com avaliação separada |
| Hoje depende de tarefas cadastradas e objetivo | Biblioteca cheia pode terminar em tela vazia | Retomada baseada em fontes e foco confirmado, mesmo sem tarefas |
| Terminal/SSH/pip usados para instalar e recuperar | Uso cotidiano depende de intervenção técnica | Serviço persistente e instalação/acesso guiados, com diagnósticos claros |

Referências de implementação: `mia/knowledge.py`, `mia/static/assets/app.js`, `mia/organization.py`, `mia/operations.py`. Não basta aumentar o número 300 ou adicionar um resumo por IA.

## Mensagem e modelo mental

Proposta de mensagem: **“Seu contexto de trabalho, reunido na Mia. Retome projetos, encontre decisões e avance com fontes.”** Complemento: **“Você escolhe onde seus dados ficam e qual IA usar.”**

Explicar antes de importar:

1. GitHub distribui o código. Não guarda automaticamente o contexto do usuário nem é uma conta da Mia.
2. Uma instalação Mia guarda o contexto e executa o serviço. O navegador ou um futuro app é a forma de acessá-la.
3. Cada participante escolhe onde instalar. No cenário remoto, arquivos enviados pelo Mac/iPhone são copiados para o servidor escolhido; no local, ficam na máquina escolhida. Isso deve ser informado antes da transferência.
4. Importar/indexar não envia conteúdo a modelos. Consultar/analisar com IA pode enviar trechos autorizados ao destino escolhido, com consentimento e uso visíveis.
5. API externa pode cobrar por uso; modelo local depende de hardware e energia. Não prometer eliminar gastos ou substituir todos os recursos de Claude/ChatGPT.

Código público e intenção de open source não substituem a licença ainda pendente. Mac/Ubuntu têm evidência técnica; suporte universal a sistemas operacionais não foi validado. Windows só será anunciado após distribuição e testes próprios.

## Uma experiência, três formas de entrar

| Escolha | Dados e execução | Disponibilidade | Papel no plano |
| --- | --- | --- | --- |
| No meu servidor | Uma instalação Linux própria, com serviço, HTTPS e backup | Enquanto servidor e rede funcionarem; independente do Mac estar aberto | Referência do proprietário, opcional para participantes |
| Neste computador | Serviço local no Mac, com inicialização automática e launcher | Depende de Mac ligado/acordado; acesso de outro dispositivo requer rede preparada | Opção de primeira classe no piloto, mesmo produto/backend |
| Conectar à minha Mia | Cliente aponta para instalação existente | Depende dessa instalação e da rede | Entrada do Mac/iPhone, sem criar outra biblioteca |

```mermaid
flowchart LR
  Mac[Mac — navegador] -->|HTTPS e sessão| Mia[Mia no servidor Linux do usuário]
  Phone[iPhone — navegador ou tela inicial] -->|HTTPS e sessão| Mia
  Mia --> Store[Contexto e banco da mesma instalação]
  Mia -->|Somente trechos autorizados| Model[Modelo local ou API opcional]
```

Mac e iPhone vendo o mesmo servidor têm acesso ao mesmo contexto. Isso não é sincronização entre dois bancos nem uso offline. Não copiar SQLite vivo via iCloud/Drive.

**Primeiro:** experiência web responsiva e dois caminhos de instalação, com serviço que sobreviva a fechamento de Terminal. No servidor, validar reinício real e HTTPS; no Mac, início de sessão e suspensão/retomada. O instalador trata processo, autenticação, origem/HTTPS quando necessários, backup e atualização. O operador configura domínio/rota conscientemente; o usuário diário entra por um endereço. CGNAT exige infraestrutura/rota adicional escolhida, sem fornecedor obrigatório. Nenhum assistente pode afirmar que abriu acesso remoto só por salvar uma preferência.

Fechar navegador ou janela do launcher não encerra o serviço. **Parar Mia** é uma ação explícita, com estado visível e aviso de que outros dispositivos perderão acesso. Sono/desligamento do Mac continua reduzindo disponibilidade; abertura automática não remove essa limitação física.

**Entrada local:** instalador/launcher Mac instala runtime, abre a Mia e mostra status, ou conecta à instalação remota. Esse caminho básico pertence ao piloto local; não depende de implementar outro frontend nativo completo. Usuário não deve precisar instalar Git/Python/pip. A distribuição precisa de origem confiável, assinatura/notarização e atualização testada. O gerenciador atual e templates são base, não esse instalador pronto. Outros sistemas terão distribuição e validação próprias; não serão simulados como suportados.

Credenciais de assinatura/notarização e infraestrutura de build são pré-requisitos externos do artefato Mac confiável. Se faltarem, continuar implementação e testes independentes, mas registrar distribuição local pendente. Não substituir o aceite em Mac limpo por instruções para ignorar a proteção do sistema.

**iPhone:** começar pelo navegador/tela inicial, com seleção de arquivos, reconexão e indisponibilidade compreensível. App nativo só quando houver necessidade comprovada de recursos como compartilhar arquivos/notificações. Serviço permanente local no iPhone e sincronização offline ficam fora deste piloto. Não anunciar PWA, launcher ou apps como já entregues.

O caminho diário dispensa Terminal; operar um servidor próprio ainda exige instalação inicial e responsabilidade operacional. Se depender do fundador para cada participante, esse aceite falhou. Hospedagem opcional futura não vira infraestrutura obrigatória nem requisito para importar.

O recrutamento pergunta a preferência de instalação antes de orientar. Registrar resultados por modalidade; sucesso no servidor não fecha aceite local e vice-versa. Um participante local sem necessidade de iPhone/remoto não deve preparar domínio, VPN ou servidor. O acesso do iPhone a uma Mia no Mac tem uma exigência de rede/disponibilidade adicional, que deve ser escolhida e explicada, não escondida no onboarding.

## Jornada: da origem até retomar o trabalho

**Chegar → trazer contexto → conferir cobertura → começar a usar → confirmar o que é atual → Hoje.**

1. **Minha Mia:** conectar à instalação existente ou instalar no destino escolhido. Mostrar onde os dados ficam; criar o acesso do proprietário nesta instalação. Nome de área, projeto, API e preços não bloqueiam a entrada.
2. **De onde vem seu trabalho?** Escolher várias origens: Obsidian/pasta Markdown, arquivos avulsos, exportação ChatGPT, exportação Claude, arquivos do Drive/outros serviços. Cada origem informa o que aceita e o que ainda não suporta. Sem pedir login da plataforma apenas para importar um export.
3. **Conferir o material:** inventário na instalação escolhida. Mostrar árvore/grupos, tipos, datas disponíveis, volume, conversas/notas reconhecidas, ignorados, conflitos e erros. Seleção por pasta, grupo ou intervalo, com exceções e prévia buscável. Nenhum checkbox obrigatório por nota. Não pedir ao usuário que divida um vault para vencer um limite do produto.
4. **Autorizar a biblioteca:** a pessoa confirma o conjunto que a Mia pode importar e consultar. Guardar proveniência; não alterar originais nem executar plugins, macros, links ou instruções em arquivos. Envio ao modelo continua uma autorização distinta.
5. **Começar progressivamente:** indexar em segundo plano com estado durável, cancelar/retomar e relatório reconciliável. Primeiros grupos autorizados e indexados tornam-se úteis enquanto os demais avançam. Mostrar cobertura parcial e pendências; sucesso parcial nunca aparece como migração completa.
6. **O que continua em andamento?** A partir do material escolhido, apresentar candidatos a projetos, decisões e assuntos; perguntar qual foco é atual. Conteúdo antigo, respostas de assistente e mtime de arquivo não estabelecem prioridades atuais. Confirmar foco não cria tarefas ou altera projetos por inferência.
7. **Primeiro resultado:** retomar um projeto reconhecível com fontes abertas, decisão anterior e questão ainda pendente. Sem IA, oferecer busca e acesso às fontes. Com IA, explicar envio/limite antes de sintetizar; propostas continuam editáveis e exigem aprovação.

Uma tela não deve exigir o vault inteiro indexado para ser útil, nem exigir uma chave para importar. Não gerar resumos de todas as notas por padrão. Priorizar estrutura, busca e recortes; IA opcional analisa o foco escolhido dentro do orçamento autorizado. Se não houver evidência suficiente, pedir orientação e manter as lacunas visíveis.

## Hoje precisa permitir continuar

Na primeira entrada, a ação principal é **“O que vamos retomar?”** e o foco escolhido. A pessoa reconhece seu trabalho em vez de encontrar somente contadores de tarefas.

- **Em andamento:** projetos/assuntos confirmados, com origem e opção de corrigir/arquivar.
- **Últimas decisões encontradas:** material relacionado ao foco, com data disponível, autoria e link para fonte. “Última encontrada” não significa decisão vigente ou cobertura completa.
- **Pendências para revisar:** questões extraídas/sugeridas, claramente diferenciadas das tarefas já aprovadas. Sem inventar prazos, urgência ou obrigações a partir do histórico.
- **Continuar uma conversa ou perguntar:** primeiro pedido com contexto recuperado e referências; threads persistentes entram no escopo da próxima experiência, não são capacidade atual.
- **Minha migração:** cobertura, origens, falhas/ignorados e novos grupos disponíveis, sem ocupar a tela principal depois de concluída.

Hoje continua útil com zero tarefas: foco, fontes recentes/relevantes e um caminho de retomada. Sem dados, pede uma origem ou uma pergunta concreta, sem inventar uma rotina pessoal. Datas respeitam fuso e distinguem data da fonte, importação e revisão humana.

Sem modelo, oferecer pastas, títulos, busca e fontes relacionadas; a pessoa escolhe o foco e marca decisões atuais. Extração semântica de projetos/pendências e síntese exigem análise autorizada ou aparecem como hipóteses heurísticas identificadas. Não prometer entendimento automático completo no modo sem IA.

## Taxonomia proposta

| Navegação | Pergunta que resolve | Conteúdo |
| --- | --- | --- |
| Hoje | O que retomar e fazer agora? | Foco, decisões, pendências revisáveis, tarefas aprovadas e primeira ação |
| Conversas | Como pensar e avançar com a Mia? | Threads, fontes usadas, propostas, retomada e custo |
| Biblioteca | Que contexto a Mia conhece e pode usar? | Origens/importações, documentos/conversas originais, organização e perfil confirmado |
| Ajustes | Onde roda e quanto/como pode usar? | Instalação/acesso, IA, limites, permissões, backup e atualização |

Busca é transversal. Em Biblioteca, separar **Fontes** (materiais originais), **Projetos e áreas** (organização de trabalho) e **Sobre mim** (declarações confirmadas). Pastas importadas não são automaticamente áreas de autorização ou projetos. Não reutilizar “Meu contexto” para três conceitos diferentes.

Trocar a linguagem de implementação: “Inteligência” → Conversas; “Sistema” → Ajustes; “Execuções” → Histórico do pedido quando necessário; estados técnicos → progresso/ação compreensível. Isto é uma mudança de arquitetura de informação e comportamento, não apenas renomear botões antes de existir conversa contínua.

A autorização no servidor continua explícita por origem/conjunto/identidade; ampliar a navegação não autoriza conteúdo excluído, em revisão ou pausado. Consultas entre pastas/projetos recuperam apenas fontes aprovadas para aquele pedido. Perfil pessoal continua opt-in, visível e revogável.

## Contrato de migração

Separar **originais**, **índice por trechos**, **conteúdo enviado ao modelo** e **memória/tarefa confirmada**. Armazenar algo não confirma sua veracidade, autoria pessoal ou atualidade.

| Origem | Primeira entrega | Cuidados e evolução |
| --- | --- | --- |
| Obsidian/Markdown | ZIP/pasta com revisão de grupos, caminhos e links entre notas; texto longo recortado | `.obsidian`, `.git`, caches e mídia fora da indexação textual, com relatório; plugins não executados. Observação contínua só de pasta explicitamente escolhida, depois |
| ChatGPT/Claude | Adaptadores versionados para exports suportados; conversas escolhidas e mensagens estruturadas | Preservar papel, datas, IDs/ramo e origem disponíveis; informar anexos/ramificações/formato não lidos. Fala antiga de IA não vira fato do usuário. Amostras reais só com autorização |
| Arquivos/pastas | Lote pelo seletor compatível ou ZIP, com progresso | Pasta do cliente não é caminho do servidor; limites do navegador/iOS exigem alternativa clara |
| Drive/outros serviços | Arquivos baixados/exportados pelo usuário entram no mesmo fluxo | `.gdoc` não contém o documento. Conector recorrente depois, com seleção real de pastas, leitura, exportação de documentos nativos, revogação e deltas; autenticação própria opcional |

Nenhum conector escreve na origem neste piloto. Mudanças posteriores produzem versões/conflictos e revisão de remoções; reimportação usa IDs estáveis disponíveis, hashes e proveniência, não posição no export. “Migrar todo o contexto” é meta de cobertura honesta, não garantia de suportar todo recurso/anexo de qualquer plataforma.

Jobs propostos: recebido, inventariando, aguardando revisão, autorizado, indexando, utilizável parcialmente, concluído/parcial/cancelado/erro. Progresso, seleção e efeito persistem após reinício; confirmações repetidas não duplicam fontes/ações. Um cancelamento mantém originais intactos e informa exatamente o que já entrou. Desfazer lote não apaga fontes independentes compartilhadas nem reescreve histórico de respostas anteriores.

Contagens têm dois níveis: **entradas** (diretórios, metadados/ocultos, formatos ignorados, arquivos elegíveis e erros de leitura) e **documentos/conversas** (reconhecidos, selecionados, não selecionados, duplicados, importados e indexados). Um JSON pode produzir muitas conversas; não somar esses números como se cada entrada fosse um documento.

Política de retenção proposta: arquivo bruto recebido fica em staging privado para retomada/revisão, separado das fontes ativas e excluído de backups permanentes por padrão; removido ao concluir/cancelar, com expiração padrão de sete dias para upload abandonado e aviso antes da expiração. Após confirmação, preservar os arquivos de texto aceitos e registros estruturados suficientes para exportação fiel, com proveniência e relato de normalizações/perdas. Anexos/metadados ignorados não ficam armazenados/exportáveis automaticamente. Retenção do ZIP inteiro é opção explícita com indicação de disco e conteúdo não indexado, sem se confundir com backup.

Em instalação remota, um ZIP inteiro recebido pode conter itens que depois serão ignorados. Explicar isso antes de enviar; escolher grupos em uma pasta no cliente pode evitar transferir exclusões. O inventário precisa informar exatamente o que foi copiado, retido, indexado, descartado ou nunca recebido. Fontes originais do usuário permanecem intactas. Exclusão/pausa afeta novos usos; retenção em backups e histórico de respostas tem explicação própria.

Quotas continuam necessárias: armazenamento, bytes recebidos/expandidos, contagem de descritores, razão de expansão, profundidade, CPU/memória e duração. Validar caminhos/links/criptografia e ZIP bombs antes de usar; filtrar lixo conhecido para contar conteúdo útil sem remover as proteções de recursos. Não trocar limites por valores arbitrários sem benchmark.

Hipótese de laboratório para orientar testes: 1k/5k/10k notas, 100 MiB de entrada e 500 MiB de texto elegível, em 2 CPU/4 GiB. Não são novos limites do produto nem promessas de desempenho. Separar corpus, memória máxima, disco necessário, tempo até primeira fonte útil e tempo até conclusão; medir antes de publicar suporte.

Antes de implementar E3/E4, pré-registrar corpus e critérios de desempenho. Metas iniciais de laboratório, a revisar antes do ensaio: em 1.000 notas/até 20 MiB de texto elegível e 2 CPU/4 GiB, primeira fonte autorizada pesquisável em até 60 s após recebimento/revisão; índice desse corpus concluído em até 10 min; processo de importação+API com RSS somado até 1 GiB. Medir transferência de rede separadamente, prever disco para staging/originais/índice e impedir início sem capacidade. No teste humano, meta de primeiro resultado útil em até 10 min a partir do acesso, sem assistência; registrar onde o tempo foi gasto e falhar o gate se exigir ajuda. Estes números são metas do teste, não garantia publicada.

## IA e custo em linguagem comum

Configuração básica: serviço/modelo compatível, chave quando necessária, quanto aceita gastar e autorização de uso. Catálogo/recomendação pode reduzir escolhas, mas nunca certificar chave/saldo/ferramentas apenas por GET `/models`. Campos de preços por milhão, tokens e endpoints personalizados ficam em opções avançadas, preservando controle.

Preços devem ter origem/data e revisão; custo ausente continua desconhecido. Limite interno é estimado quando depende desses preços, separado de limite/fatura no provedor. Não habilitar um modo pago sem política de orçamento implementada e compreensível. Importar não gasta tokens; análise opcional mostra destino, grupos/trechos, limite e estado de consentimento. Sem ampliação de teto, retry de geração ou mudança de modelo silenciosa.

Comparar gasto, qualidade e esforço com as assinaturas que participantes de fato substituíram. Não presumir que API paga/local é sempre mais barata nem confundir assinatura com crédito de API.

## Ordem de execução que altera o próximo ciclo

Preservar M0–M5 e sua evidência, mas deixar de usar uma sequência rígida M2 → M3 → M4 como critério de sucesso. M3 (migração/primeiro valor) e M4 (serviço/acesso) bloqueiam juntos o novo piloto.

| Entrega | Escopo | Gate para avançar |
| --- | --- | --- |
| E1 — Jornada e mensagem | Protótipo da migração até Hoje, nova taxonomia, localização dos dados, corpus de aceitação autorizado/sintético | Usuário identifica seu primeiro resultado e entende o que foi transferido, o que falta e onde fica; nenhuma capacidade planejada se apresenta como pronta |
| E2 — Entrar sem Terminal diário | Dois caminhos: Linux com serviço/login/HTTPS e Mac local com instalador/launcher/runtime; diagnóstico, atualização/recuperação e mesma UI móvel | Fechar SSH/Terminal não perde serviço/contexto; reinício Linux e login/suspensão Mac validados separadamente; acesso entre dispositivos somente quando escolhido e comprovado |
| E3 — Migrar em escala | Jobs/transferência retomáveis, revisão agrupada, Obsidian/Markdown e adaptadores de exports, contagens/proveniência | Vault representativo passa sem dividir ou selecionar nota por nota; interrupção/repetição/cancelamento seguros, limites medidos |
| E4 — Retomar com contexto | Índice por trechos, busca avaliada, threads, foco/projetos confirmados e Hoje ligado a fontes | Primeira pergunta útil e decisão/pendência localizáveis; cobertura parcial/idade/lacunas visíveis; nenhum efeito sem revisão |
| E5 — Manter contexto e ampliar entrada | Reimportação incremental; conector Drive de leitura quando credenciais/escopo existirem; conveniências de clientes além do launcher básico | Alteração/remoção/conflito controlados, revogação efetiva, artefatos distribuídos e operação real conferidos |
| E6 — Piloto independente | 2–3 pessoas, fontes próprias, instalação/acesso sem fundador, orçamento/qualidade e backup externo | Primeiro valor real, entendimento e continuidade; somente então decidir release, apps adicionais e alegações de economia |

E2 e E3 podem avançar em paralelo depois do desenho E1; E4 exige grupos autorizados úteis, não todo conector futuro. Adaptadores de arquivos e exports entram no núcleo da migração. O launcher/instalador local é gate E2; Drive vivo tem gate E5. Nenhum é apresentado como já suportado. iPhone nativo e sync offline não entram para compensar falhas de onboarding.

E6 pode começar após o núcleo E2–E4 usando arquivos/exports suportados. Não bloquear aprendizado independente pelo OAuth recorrente do Drive ou recursos adicionais E5; registrar esse escopo e a preferência real do participante. Um piloto exclusivamente remoto não fecha aceite local: sem participante/artefato local, ele continua explicitamente pendente.

## Critérios de aceitação e revisão

- Vault de pelo menos 1.500 notas elegíveis, com pastas/metadados/mídia adicionais, não exige divisão manual. Contagens elegíveis, ignoradas, duplicadas, falhas e importadas reconciliam; nenhum arquivo some silenciosamente.
- O volume/distribuição do vault recusado deve ser inventariado privadamente com autorização e representado por corpus sintético equivalente. Não transportar seu conteúdo ou nomes privados ao repositório. Passar somente 1.500 notas sintéticas não comprova suporte àquele vault.
- Rede interrompida, servidor reiniciado, seleção/confirmar repetidos e cancelamento têm resultado recuperável, sem efeitos duplicados. Origem intacta; conteúdo não autorizado nunca entra em índice/IA.
- Exports ChatGPT/Claude escolhidos preservam autoria/papéis/datas disponíveis e relatam perdas. Compatibilidade específica é registrada por versão/formato, sem generalizar a todas as plataformas.
- Recuperação de fato/decisão em trecho não inicial, entre pastas, com sinônimos, fontes antigas/conflitantes e ausência de resposta é avaliada separadamente da importação. Fonte aberta sustenta a resposta; a Mia admite lacuna.
- Hoje oferece retomada ligada ao foco e às fontes, mesmo com zero tarefas/IA. Sugestões não viram tarefas, perfil ou urgência automaticamente; perfis e envio externo têm consentimento próprio.
- Mac e iPhone acessam a mesma instalação Linux após fechar Terminal e reiniciar o serviço/servidor. HTTPS/origem/sessão e backup externo/restauração são comprovados na infraestrutura escolhida; não por PID, formulário salvo ou ensaio loopback.
- Participante local instala sem comandos, fecha Terminal, retorna após novo login/suspensão e mantém seu contexto; nunca precisa de servidor/domínio só para usar no próprio Mac. Backup/atualização/retorno são validados também no artefato local. Resultados não são generalizados entre modalidades.
- Participantes explicam onde estão os dados, o que foi importado/ignorado, o que pode chegar ao modelo e como pausar/remover. Registro de tempo até primeiro valor, ajuda, erros e custo sem copiar conteúdo privado ao repositório.
- O proprietário refaz o onboarding redesenhado e avalia a experiência; 2–3 participantes independentes verificam instalação e primeiro valor. Nenhum marco fecha somente por suíte técnica ou mockup.

Falta definir com os participantes o corpus e a necessidade concreta de retomada, medir escala e obter os aceites externos. Licença/atribuição e distribuição confiável continuam gates próprios. A aprovação desta proposta não autoriza abrir portas, importar fontes privadas ou publicar instalações reais.
