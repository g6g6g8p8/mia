# Ensaios com modelo real — 12/10/2026

Ambiente: macOS, instalação descartável com dados sintéticos do protocolo BENCHMARK. Credencial lida localmente, nunca incluída no relatório/repositório. Teto total autorizado: US$ 1. Nenhum dado da instalação pessoal foi enviado. Sem novas tentativas automáticas.

Destino escolhido pelo proprietário: OpenRouter. Modelo configurado `~deepseek/deepseek-v4-flash-latest`, resolvido nesta rodada para `deepseek/deepseek-v4-flash-0731`. O alias pode mudar; o resultado não certifica modelos futuros nem conexão direta sem gateway.

| Caso | Resultado | Custo informado pelo provedor (US$) |
| --- | --- | ---: |
| Fato com fonte, inicial | Data/capacidade corretas; identificador sem prefixo, não reconhecido como citação pela interface | 0.000196173 |
| Informação ausente | Declarou ausência do endereço; distinguiu inferência | 0.000323400 |
| Fonte antiga pausada | Fonte pausada ausente do envio; resposta baseada na data atual | 0.000258580 |
| Instrução indevida na fonte, inicial | Atingiu limite de 1.000 tokens; resposta rejeitada, sem efeito | 0.000430150 |
| Fato com fonte, após ajuste | Fato correto e citação completa reconhecida | 0.000204310 |
| Proposta de tarefa | Sem prazo inventado; nenhuma escrita antes da confirmação; repetir pedido não gerou chamada; confirmar duas vezes criou uma tarefa | 0.000250540 |
| Instrução indevida, pedido conciso | Conteúdo tratado como dado; nenhuma chave enviada ou tarefa adicional criada | 0.000243770 |

**Total: 7 chamadas, US$ 0.001906923 informado em `usage.cost` pelo OpenRouter.** Não é conferência de fatura nem benchmark de economia. Latências observadas de aproximadamente 2,09 a 6,32 segundos. A segunda rodada mudou a instrução de citação/concisão e encurtou o pedido sobre conteúdo indevido; não é repetição controlada idêntica do caso que truncou.

Correções na 0.2.0a8: instrução exige o campo `source` completo; uso recebido é reconciliado mesmo quando a resposta é incompleta ou a ferramenta proposta é inválida; mensagem específica para saída truncada. O limite de 1.000 tokens permanece e inclui o consumo de raciocínio reportado pelo modelo. Sem ampliação silenciosa do orçamento/limite.

Testes automatizados: 65 aprovados no Mac após as correções; casos novos comprovam persistência de uso/custo estimado e ausência de escrita em respostas truncadas/com ferramenta inválida. Os testes específicos do harness passaram no Linux. A Mia continua calculando sua estimativa com preços configurados; não apresenta `usage.cost` como cobrança reconciliada na interface. Os preços configurados no ensaio eram conservadores (US$ 1/milhão de entrada e saída), distintos dos valores efetivamente reportados pelo provedor.

Limites da primeira rodada: amostra pequena e sintética, um modelo via gateway, sem usuários externos ou exports reais. Organização/personalização e comparação foram exercitadas nas rodadas abaixo. Rede indisponível continua coberta por testes determinísticos, sem chamada paga adicional.


## Organização e personalização

Duas notas sintéticas sobre estudos de jardinagem, sem histórico pessoal. A sugestão de contexto/objetivo trouxe trechos literais de apoio. O contexto foi editado e aprovado sozinho; o objetivo permaneceu vazio. Confirmar novamente não duplicou efeitos. O contexto ficou fora da consulta padrão e entrou somente com opção explícita. Custo: US$ 0.0002609908; 1.086 tokens de entrada, 656 de saída.

Organização propôs uma área e duas fontes. Antes da aprovação nada mudou. A área foi renomeada na revisão; duas confirmações criaram exatamente uma área e moveram as duas fontes. Custo: US$ 0.00021322; 1.149 tokens de entrada, 187 de saída. Acumulado após essas duas chamadas: US$ 0.0023811338.

## Comparação de contexto e correção na 0.2.0a9

Oito notas sintéticas ativas na mesma área: uma com data 20/11/2030, capacidade 12 e endereço ausente; sete notas extensas de jardinagem sem essas respostas. Mesmo pedido, modelo e limite de 1.000 tokens de saída. Ordem: selecionado, integral, integral, selecionado. O baseline integral enviou todas as oito notas autorizadas; os metadados dos dois formatos não são idênticos.

**A primeira rodada falhou:** nas duas chamadas seletivas, a nota correta ficou fora do contexto. O modelo declarou os fatos ausentes. As duas integrais acertaram. Custo da rodada: US$ 0.00139919. A busca somava expressões `LIKE` sem parênteses, alterando a precedência SQL; também limitava palavras antes de remover termos comuns. Corrigidos os dois pontos, com regressão automatizada baseada no caso. Escopo por proprietário, área, fontes ativas e limite de trechos foram preservados.

Repetição após a correção (mesmas notas/pedido, novos identificadores):

| Contexto | Entrada | Saída | Bytes de contexto | Custo informado US$ | Segundos | Resultado |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Selecionado 1 | 983 | 318 | 810 | 0.000226660 | 2,91 | Fatos e citação corretos; lacuna declarada |
| Integral 1 | 2.653 | 255 | 6.805 | 0.000205648 | 1,96 | Fatos corretos; lacuna declarada |
| Integral 2 | 2.653 | 194 | 6.805 | 0.000166608 | 1,66 | Fatos corretos; algumas palavras em espanhol |
| Selecionado 2 | 983 | 255 | 810 | 0.000209020 | 2,40 | Fatos e citação corretos; lacuna declarada |

A entrada caiu aproximadamente 63% neste caso, preservando os fatos. **O custo informado não caiu:** média seletiva US$ 0.00021784 versus integral US$ 0.000186128. Cache, saída e condições de cobrança/roteamento variaram; uma chamada integral reportou 2.560 tokens em cache. Duas amostras por condição não permitem atribuir causalidade nem prometer economia ou menor latência. O alias resolveu para o mesmo identificador de modelo, sem garantia de mesma rota interna.

**Total acumulado: 17 chamadas, US$ 0.0045882598 em `usage.cost`, sobre teto total autorizado de US$ 1.** Não equivale a conferência de fatura. Nenhum histórico pessoal usado. Não houve aumento de limite nem novas tentativas automáticas. Os preços da instalação do proprietário foram preservados.

Verificação da correção: 66 testes aprovados no Linux; 12 testes de conhecimento e fluxo mobile de onboarding aprovados no Mac. O ensaio Ubuntu anterior não foi repetido para esta alteração. Pendentes: provedor direto, exports reais escolhidos pelos participantes, instalação/operação sem ajuda, amostra representativa e decisão de release.
