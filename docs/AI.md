# IA opcional — M2 inicial

A instalação funciona sem IA. Nenhuma chave, conta do projeto, gateway ou máquina do desenvolvedor é exigida.

## Configuração pelo proprietário

No `.env` local, configure `MIA_AI_BASE_URL`, `MIA_AI_MODEL`, `MIA_AI_API_KEY`, `MIA_AI_DAILY_CALL_LIMIT` e então `MIA_AI_ENABLED=true`. O endereço base deve terminar no prefixo da API, normalmente `/v1`, sem `/chat/completions`. Reinicie o serviço após alterar a configuração. Nenhuma conexão é feita só por abrir a interface.

O servidor usa HTTPS; HTTP só é permitido para loopback e `host.docker.internal`. Não reutilize credenciais de outros sistemas automaticamente. Use uma chave própria e limite de gasto no provedor. Não compartilhe `.env`, saída de `docker compose config` ou diagnóstico de ambiente. A chave fica em variável de ambiente do processo, não no navegador, histórico de execuções ou exportação. Administradores da máquina ainda podem acessá-la.

O adaptador exige Chat Completions com ferramentas e `max_completion_tokens`. Referência de protocolo: [Create chat completion](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create). A compatibilidade deve ser testada por provedor/modelo; não há promessa de que todas as APIs aceitem os mesmos parâmetros. Sem fallback ou nova tentativa automática.

IA local é opcional e avançada. Um servidor local compatível pode ser usado, mas não instalamos modelos nem recomendamos uma configuração sem medir a qualidade. Dentro de Docker, `127.0.0.1` é o contêiner, não o computador hospedeiro; configurar a rede local é uma decisão explícita do administrador.

## Fluxo

1. Abra Inteligência e confira o destino e modelo.
2. Escolha uma área e visualize o contexto.
3. Autorize o envio da mensagem e do contexto; só então envie.
4. Revise a resposta e as fontes que foram enviadas.
5. Se houver proposta de tarefa, confirme ou recuse.

Contexto: metadados da área e até 12 tarefas recentes, com até 500 caracteres de notas por tarefa. Não é busca semântica nem recuperação de documentos externos. Outras áreas, e-mail, senha e histórico de conversa não são enviados. As fontes exibidas são evidência do contexto enviado, não certificação da veracidade da resposta. O modelo recebe a data no fuso do proprietário.

## Limites implementados

- Uma chamada por pedido, uma proposta no máximo, sem loops ou fallback.
- 4.000 caracteres por pedido, até 1.000 tokens de saída solicitados ao provedor.
- Tempo total de chamada limitado a 45 segundos, resposta limitada a 256 KB.
- 20 chamadas por dia UTC por padrão, configurável entre 1 e 1.000.
- Reserva transacional da chamada; no máximo uma chamada em andamento por proprietário.
- Falhas e chamadas interrompidas também consomem a cota: podem ter sido cobradas.
- Identificador idempotente por pedido; aprovação repetida não duplica a tarefa.
- Só `propose_task` é aceito. Não há acesso a shell, arquivos externos ou conectores.
- A proposta fica no banco e pode ser decidida depois. Ao reiniciar, chamadas em andamento viram falha explícita e não são reenviadas.
- Use apenas um processo/worker da aplicação nesta versão.

## O que ainda não está pronto

O custo monetário aparece como **desconhecido**, nunca zero. Contagem de tokens, quando presente, é a informada pelo provedor. Não há precificação, reserva em dinheiro, medição de economia, limite financeiro na Mia ou seleção automática de modelo. O limite de chamadas não substitui um limite financeiro no provedor.

Configuração ainda via `.env`, sem assistente gráfico de credenciais. Não há conversa contínua, memória aprendida, edição da proposta, restauração automática, tarefas autônomas ou retomada de uma geração interrompida. Testes com respostas simuladas validam contratos, não a inteligência de um modelo.
