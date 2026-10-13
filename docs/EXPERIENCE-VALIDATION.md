# Evidência da nova experiência — 0.2.0a12

13/10/2026. Material inteiramente sintético, em Linux com Python 3.12.14. Não foram lidos vaults pessoais nem credenciais, nem feitas novas chamadas a provedores pagos. Instalações do Mac e servidor do proprietário não são atualizadas pelo desenvolvimento no cloud.

## Fluxo completo

`scripts/browser_experience.py` usa Chromium desktop e viewport móvel de 390 px. Passou: acesso sem área obrigatória, localização dos dados, envio de ZIP com 1.500 notas, revisão paginada/buscável por grupos, 1.000 fontes autorizadas, seleção persistida após recarregar, leitura do original, foco além das primeiras 20 fontes, edição durante salvamento e avanço, Hoje com zero tarefas e cobertura parcial visível.

Um reinício real de uvicorn verificou retomada de upload incompleto. Reimportação/desfazer preservaram fontes compartilhadas. Conversas continuaram com consentimento por pedido, foco opt-in, custo estimado e limite diário; pausa de fontes impediu reaparecimento pelo histórico. O provedor foi um servidor HTTP local determinístico. Não valida qualidade de um modelo real.

No ensaio final completo: ZIP de 503.724 bytes; inventário 12,966 s; primeira fonte pesquisável após confirmação 0,624 s; indexação dos grupos 4,013 s; RSS amostrado do processo 67.760 KiB. Transferência/revisão e indexação são tempos separados, sem alegação de resposta instantânea para qualquer vault.

## Capacidade e recursos

`scripts/benchmark_migration.py` pré-declara corpus e gates antes do ensaio: 20 MiB de texto UTF-8 por corpus, notas distintas com evidência tardia, ZIP sem compressão mais metadados/mídia ignorados. Um uvicorn real executa API e worker; afinidade em duas CPUs, limite de espaço de endereçamento de 4 GiB. RSS é amostrado; isso não representa uma máquina física exclusivamente dedicada com 4 GiB.

| Notas | Inventário antes da revisão | Primeira busca após autorização | Índice concluído | RSS máximo amostrado | Hoje autenticado P95 |
| --- | --- | --- | --- | --- | --- |
| 1.000 | 8,519 s | 0,993 s | 5,330 s | 61,0 MiB | 12,855 ms |
| 1.500 | 12,591 s | 0,967 s | 7,187 s | 60,1 MiB | 11,848 ms |
| 5.000 | 46,940 s | 1,077 s | 19,656 s | 66,7 MiB | 12,564 ms |
| 10.000 | 112,036 s | 1,057 s | 36,155 s | 70,3 MiB | 17,656 ms |

Gates de laboratório passaram: primeira busca após autorização até 60 s; indexação até 600 s; RSS até 1 GiB; Hoje P95 até 250 ms. Transferência loopback variou de 0,071–0,083 s e não representa internet. Pico de disco variou de 146,0–249,3 MiB, considerando staging/índice/banco. Cada corpus tinha 20 MiB de texto, não 100 MiB recebidos ou 500 MiB expandidos; os máximos de quota não foram certificados como desempenho.

Há regressão de export monolítico JSON acima de 8 MiB com 800 conversas, sem divisão manual; cauda inválida não autoriza/publica conversas daquele arquivo. Papéis, IDs, datas, ramo escolhido e omissões são verificados e exportados. Compatibilidade continua específica dos esquemas suportados.

## Revisão, recuperação e distribuição

Revisões independentes encontraram e corrigiram: seleção wildcard invisível; quotas não reservadas entre jobs; foco limitado às primeiras fontes; ocultação de erros parciais; corrida entre salvar foco e avançar; inconsistência de exclusão pelas APIs antigas; pausa persistida indevidamente no fim da sessão; staging em snapshot de migração manual; estados pendentes após restaurar sem staging; limpeza antes do commit terminal; exportação acumulando biblioteca em RAM e perda dos vínculos pausados de foco no export.

A suíte completa passou com **293 testes**. Uma revisão independente final também passou 40 testes dirigidos e verificou upload não autenticado sem consumir o corpo, origem estrangeira bloqueada e bloco excessivo sem avanço de progresso. A revisão encontrou um fixture que mantinha SQLite aberto ao simular origem parada; a conexão foi encerrada explicitamente, mantendo a recusa de arquivos especiais no produto.

Testes cobrem propriedade/origem, ZIP inválido/travessia/symlinks/expansão, checksum e offsets, checkpoints, cancelamento/desfazer, documentos deduplicados, histórico revogado, orçamento/idempotência, foco e export/restauração. Exportação preserva mais de 20 MiB de conteúdo com pico de alocação Python inferior a 16 MiB nesse ensaio, escrevendo ZIP em arquivo temporário privado; falha de espaço preserva dados e libera a operação.

`scripts/native_lifecycle.py --baseline-ref 6f50fd2 --wheelhouse ...` passou com instalação nova offline de a11, atualização a12, HTTP/contexto, falha de startup, recuperação durável, rollback reconhecido e supervisor interrompido com SIGKILL. Os testes do novo supervisor usam processos reais isolados: encerrar o comando não para o backend, fim da sessão permite novo início, parada explícita permanece pausada e falhas não geram reinícios ilimitados. Não alteram serviço do host.

Wheel/sdist e imagem Docker são conferidos com arquivos públicos explícitos, runtime fixado, avisos/licenças de terceiros e exclusão de dados privados selecionados. Docker offline usa hashes já verificados e mantém validação de confiança, usuário sem privilégios, HTTP/assets e persistência após reinício.

## Aceites externos preservados

Continuam abertos: vault real representativo; exports próprios autorizados; primeiro valor/compreensão sem ajuda com 2–3 participantes; ativação e boot systemd/launchd reais; assinatura/notarização e instalação limpa Mac; suspensão/retomada; Safari/iPhone físico; HTTPS/rede externa escolhidos; backup fora da máquina; qualidade/custo com modelos reais da nova jornada. Apache-2.0 foi aplicada posteriormente à validação inicial, por escolha delegada do proprietário; preservar avisos do artefato concreto continua obrigatório.

Launcher e empacotador Mac são fundação técnica, não artefato público assinado pronto. Drive recorrente, deltas/remoções revisáveis entre versões e sync offline continuam planejados. Esses aceites não impedem revisar/testar o núcleo em uma instalação preparada, mas impedem declarar release ampla ou economia comprovada.
