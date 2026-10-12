# IA opcional — M2 inicial

A instalação funciona sem IA. Nenhuma chave, conta do projeto, gateway ou máquina do desenvolvedor é exigida.

OpenRouter é opcional. Em Sistema e no onboarding, escolha continuar sem IA, OpenAI direto, outro serviço/gateway compatível ou servidor local. OpenAI preenche apenas o endereço; modelo, chave e preços são escolhidos pelo proprietário. Outros serviços exigem endereço próprio. A seleção exibe instruções e limpa chave digitada/modelo ao trocar de destino. APIs com protocolos diferentes precisam de adaptadores próprios, ainda não implementados. Não há teste automático de conexão nem catálogo de modelos.

## Configuração pelo proprietário

Use **Sistema → Configurar IA** ou a etapa de IA no onboarding. Informe endereço base (prefixo como `/v1`, sem `/chat/completions`), modelo, chave e limite diário. Salvar não faz chamada. A configuração gráfica prevalece sobre o ambiente e é salva em `MIA_DATA_DIR/ai-settings.json`, permissão `0600`. Sem criptografia implementada pelo aplicativo; o administrador da máquina pode ler esse arquivo.

O `.env` continua como configuração inicial alternativa. A chave nunca é retornada pela API ou incluída no histórico/exportação. Campo vazio mantém a chave apenas no mesmo destino; mudança de destino exige outra chave. Não alterar configuração durante uma geração.

O destino usa HTTPS; HTTP só é permitido para loopback e `host.docker.internal`. Use chave própria e limite no provedor. Não compartilhe `.env`, `ai-settings.json` ou diagnóstico de ambiente.

O adaptador exige Chat Completions com ferramentas e `max_completion_tokens`. Referência de protocolo: [Create chat completion](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create). A compatibilidade deve ser testada por provedor/modelo; não há promessa de que todas as APIs aceitem os mesmos parâmetros. Sem fallback ou nova tentativa automática.

IA local é opcional e avançada. Um servidor local compatível pode ser usado, mas não instalamos modelos nem recomendamos uma configuração sem medir a qualidade. Dentro de Docker, `127.0.0.1` é o contêiner, não o computador hospedeiro; configurar a rede local é uma decisão explícita do administrador.

## Fluxo

1. Abra Inteligência e confira o destino e modelo.
2. Escolha uma área e visualize o contexto.
3. Autorize o envio da mensagem e do contexto; só então envie.
4. Revise a resposta e as fontes que foram enviadas.
5. Se houver proposta de tarefa, confirme ou recuse.

Contexto: área, até 12 tarefas com notas limitadas e até três trechos de fontes importadas encontrados pelo pedido. Sem busca semântica ou conector externo. O contexto pessoal e objetivo só entram quando o usuário marca **Incluir meu contexto pessoal e objetivo confirmados nesta consulta**; aparecem na prévia como `profile:1`. Fontes de outras áreas, dados de autenticação e histórico completo não são adicionados. Referências inexistentes são indicadas; isso não certifica a interpretação. O modelo recebe a data no fuso do proprietário.

## Limites implementados

- Uma chamada por pedido, uma proposta no máximo, sem loops ou fallback.
- 4.000 caracteres por pedido, até 1.000 tokens de saída solicitados ao provedor.
- Tempo total de chamada limitado a 45 segundos, resposta limitada a 256 KB.
- 20 chamadas por dia UTC por padrão, configurável entre 1 e 1.000.
- Reserva transacional da chamada; no máximo uma chamada em andamento por proprietário.
- Falhas e chamadas interrompidas também consomem a cota: podem ter sido cobradas.
- Identificador idempotente por pedido; aprovação repetida não duplica a tarefa.
- Cada pedido habilita uma ferramenta: `propose_task`, `propose_organization` ou `propose_personalization`, conforme a função escolhida. A resposta não pode trocar de ferramenta. Não há acesso a shell, arquivos externos ou conectores.
- A proposta fica no banco e pode ser decidida depois. Ao reiniciar, chamadas em andamento viram falha explícita e não são reenviadas.
- Use apenas um processo/worker da aplicação nesta versão.

## O que ainda não está pronto

Sem preços configurados, custo é **desconhecido**, nunca assumido zero. Com preços informados em US$/milhão de tokens, a Mia reserva um envelope estimado de 32.768 tokens de entrada e 1.000 de saída antes da chamada, transacionalmente. Contexto serializado acima de 24.000 bytes é interrompido. O envelope é uma hipótese conservadora, não contagem exata nem garantia de cobrança.

Com contagens completas de entrada/saída, reconcilia o custo estimado pelos preços congelados na execução e libera a diferença. Falhas ou uso incompleto conservam a reserva. Uso acima do envelope bloqueia chamadas da instalação para revisão administrativa. Chamadas anteriores do dia com custo desconhecido impedem novas chamadas sob orçamento calculável. Dia UTC.

Não há confirmação da fatura, custos adicionais de ferramentas, atualização automática de preços, seleção automática de modelo ou benchmark de economia. Configure também limite financeiro no provedor.

Não há conversa contínua, memória aprendida, edição da proposta de tarefa, tarefas autônomas ou retomada de geração interrompida. Propostas de organização podem ser editadas antes da confirmação. Backup/restauração são por comando. Testes simulados validam contratos, não a inteligência de um modelo.

## Organização assistida — M3

Em **Áreas → Fontes → Organizar minhas fontes**, escolha até seis fontes ativas da mesma área, veja a prévia e autorize a geração. O envio contém apenas os primeiros 1.800 bytes UTF-8 de cada fonte escolhida, metadados dessas fontes e o pedido. A API não envia tarefas, fontes não selecionadas ou o histórico completo. Trechos truncados são identificados; a proposta pode ser incompleta.

Uma chamada compartilha cota, reserva e reconciliação com Inteligência. A ferramenta propõe até quatro novas áreas, cada uma com nome, descrição e IDs de documentos selecionados. Campos extras, IDs externos e distribuição duplicada são rejeitados pelo servidor. Falhas não criam áreas nem movem fontes.

Na revisão, selecione as áreas desejadas, edite nomes/descrições e desmarque documentos que devem permanecer no lugar. Confirmar cria novas áreas e move apenas os documentos escolhidos, mantendo conteúdo, IDs e proveniência da importação. Nomes já existentes exigem edição: esta versão não mescla áreas. Fontes pausadas, excluídas ou movidas desde a geração bloqueiam a confirmação correspondente. Confirmação repetida com o mesmo conteúdo é idempotente; uma seleção diferente após aplicação recebe conflito.

Descrições aprovadas passam a ser contexto próprio das áreas. Pausar ou excluir a fonte original não apaga essas descrições; revise-as em **Áreas → Editar área**. Proposta original, trechos enviados e seleção aplicada ficam no histórico/exportação. Não são inferidos perfil pessoal, novos objetivos, prazos ou tarefas nesta função.

## Contexto pessoal e objetivo — M3

Em **Sistema → Meu contexto** ou **Fontes → Personalizar minha Mia**, selecione até seis fontes da mesma área, confira a prévia e autorize a geração. Usa os mesmos limites de trechos, orçamento e cota da organização. O contexto já confirmado e o objetivo atual não são enviados automaticamente nessa geração; apenas pedido, metadados e trechos das fontes selecionadas.

Cada sugestão contém texto de até 1.000 caracteres e de um a três trechos literais de apoio, com IDs de fontes selecionadas. O servidor rejeita IDs externos, trechos ausentes e campos desconhecidos. Presença do trecho não comprova a conclusão: a pessoa revisa autoria, atualidade e interpretação antes de confirmar.

Os campos começam desmarcados. O usuário pode editar texto, aplicar somente contexto ou somente objetivo, ou recusar tudo. Confirmar substitui somente os campos escolhidos. Revisões locais impedem que uma proposta antiga sobrescreva uma edição posterior; fontes pausadas, removidas ou movidas também bloqueiam a aprovação relevante. Confirmação repetida é idempotente e não repete a escrita.

Contexto confirmado não é enviado por padrão em Inteligência; a inclusão é por pedido e visível na prévia. Editar ou limpar o contexto é uma operação local sem geração; não apaga snapshots de execuções anteriores. O objetivo continua editável no onboarding. Estado atual, proposta original, evidências enviadas e seleção aplicada são preservados na exportação e no backup. Não há aprendizado automático, avaliação psicológica nem detecção semântica garantida de autoria em históricos.
