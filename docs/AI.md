# IA opcional — M2 inicial

A instalação funciona sem IA. Nenhuma chave, conta do projeto, gateway ou máquina do desenvolvedor é exigida.

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

Contexto: área, até 12 tarefas com notas limitadas e até três trechos de fontes importadas encontrados pelo pedido. Sem busca semântica ou conector externo. Outras áreas, e-mail, senha e histórico completo não são enviados. Referências inexistentes são indicadas; isso não certifica a interpretação. O modelo recebe a data no fuso do proprietário.

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

Sem preços configurados, custo é **desconhecido**, nunca assumido zero. Com preços informados em US$/milhão de tokens, a Mia reserva um envelope estimado de 32.768 tokens de entrada e 1.000 de saída antes da chamada, transacionalmente. Contexto serializado acima de 24.000 bytes é interrompido. O envelope é uma hipótese conservadora, não contagem exata nem garantia de cobrança.

Com contagens completas de entrada/saída, reconcilia o custo estimado pelos preços congelados na execução e libera a diferença. Falhas ou uso incompleto conservam a reserva. Uso acima do envelope bloqueia chamadas da instalação para revisão administrativa. Chamadas anteriores do dia com custo desconhecido impedem novas chamadas sob orçamento calculável. Dia UTC.

Não há confirmação da fatura, custos adicionais de ferramentas, atualização automática de preços, seleção automática de modelo ou benchmark de economia. Configure também limite financeiro no provedor.

Não há conversa contínua, memória aprendida, edição da proposta, tarefas autônomas ou retomada de geração interrompida. Backup/restauração são por comando. Testes simulados validam contratos, não a inteligência de um modelo.
