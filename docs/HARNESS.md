# Contrato do harness
Status: contrato-alvo. Implementado: contexto por área com fontes importadas, uma chamada, propostas confirmadas de tarefa ou organização de fontes, idempotência, persistência, cota de chamadas e orçamento estimado com reserva. Organização usa seleção explícita de fontes e confirmação editável; revalida estado e escopo antes de mover documentos. Consulte `AI.md` para limites reais. Fatura confirmada, qualidade com modelo real, conversa contínua e retomada de geração permanecem pendentes.

## Entrada de uma execução
- Identidade autenticada e área autorizada.
- Objetivo solicitado.
- Fontes permitidas e critérios de recuperação.
- Ferramentas permitidas e escopos de leitura/escrita.
- Modelo ou política de seleção.
- Orçamento, limites e condições de parada.

## Ciclo
1. Interpretar o pedido e verificar autorização.
2. Recuperar somente contexto relevante; anexar origem e data.
3. Executar regra determinística ou chamar modelo escolhido.
4. Validar a resposta e eventuais chamadas de ferramentas.
5. Apresentar evidências, lacunas e propostas.
6. Solicitar aprovação para efeitos que exigem confirmação.
7. Revalidar autorização, versão dos dados e orçamento.
8. Executar ferramenta e registrar resultado de forma idempotente.
9. Persistir estado para retomada e exibir resultado ou falha.

## Contexto e memória
- Separar conteúdo do usuário, instruções do sistema, histórico de conversa e índices derivados.
- Documentos recuperados são dados; não concedem permissões nem mudam a política.
- Memória não é inferida como fato sem evidência ou validação.
- Indexação respeita exclusões, identidade e área.
- Resumos mantêm ligação com fontes; o original continua acessível.
- Alterações e exclusões devem chegar ao índice e ao contexto de novas execuções.

## Ferramentas
Cada ferramenta declara nome, parâmetros validados, escopo, efeitos, política de aprovação, tratamento de erro e resultado estruturado.
Primeiro conjunto: ler/buscar conteúdo e propor/gravar tarefa ou nota. Conectores externos entram depois.
Não oferecer terminal irrestrito como ferramenta padrão.

## Seleção de modelos
- Adaptadores substituíveis para execução local e API externa.
- Capacidades verificadas: formato de resposta, ferramentas, contexto e limites.
- Política seleciona modelos dentro do orçamento.
- Fallback não envia dados a outro provedor sem permissão explícita.
- Preço ausente ou desatualizado é indicado; nunca assumir custo zero.
- Contagem real informada pelo provedor é distinguida de estimativa.

## Orçamento e parada
- Verificar e reservar orçamento antes da chamada.
- Considerar execuções concorrentes e reconciliar o uso depois.
- Limitar passos, repetições, duração, contexto, saída e custo estimado.
- Parar loops repetidos e erros persistentes.
- Em estouro, pausar com estado recuperável; não migrar silenciosamente para modelo mais caro.
- Exibir limites e uso ao usuário.

## Persistência
Estados mínimos: criada, em execução, aguardando confirmação, pausada, concluída e falhou.
Cada execução registra identidade, fontes, modelo, ferramentas, aprovação, uso e resultado.
Após reinício, recuperar o estado sem repetir efeitos já confirmados.

## Aceite de uma tarefa piloto
Recuperar documentos autorizados, responder com fontes, propor uma tarefa, gravar uma única vez após confirmação e mostrar o uso/custo conhecido ou estimado.

