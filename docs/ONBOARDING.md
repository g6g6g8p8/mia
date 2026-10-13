# Onboarding com contexto próprio

0.2.0a12 · 13/10/2026. A avaliação 2/10 do uso do zero motivou a nova jornada. Esta implementação é uma alpha: testes sintéticos não substituem fontes reais, compreensão e primeiro resultado de participantes.

## Entrar e retomar

Criar acesso pede nome, senha e fuso. Não exige criar uma área nem configurar modelo. Uma biblioteca inicial interna mantém a autorização; pastas importadas não viram projetos automaticamente.

A preparação pode ser retomada ou encerrada para começar a usar:

1. **Trazer contexto:** confirmar onde a instalação existente está rodando, escolher origem/arquivo/pasta, acompanhar envio e inventário.
2. **IA opcional:** continuar com busca local ou configurar serviço/modelo próprio; preços e orçamento ficam em opções avançadas. APIs podem cobrar por uso; assinatura de chat não é crédito de API.
3. **Meu foco:** escolher trabalho atual e fontes de apoio; buscar/paginar toda a biblioteca, conferir originais e confirmar até 20 fontes.
4. **Retomar:** abrir Hoje, buscar ou começar uma conversa. Importação não cria tarefas nem confirma fatos pessoais.

A navegação é **Hoje / Conversas / Biblioteca / Ajustes**, com busca transversal. Biblioteca reúne Fontes, Projetos e áreas e Sobre mim. Instalação local e servidor são escolhas igualmente válidas; marcar uma opção informa onde esta instalação já está rodando, sem instalar, mover dados ou abrir acesso remoto.

Em servidor, arquivos enviados ficam naquela máquina. Mac e iPhone acessando o mesmo endereço usam a mesma biblioteca; duas instalações não sincronizam seus bancos. GitHub contém código, não recebe automaticamente dados. Uso sem Terminal diário depende da preparação do serviço em [INSTALL-BACKGROUND.md](INSTALL-BACKGROUND.md).

## Origem e cobertura

| Origem | Entrada atual | Limites de interpretação |
| --- | --- | --- |
| Obsidian/Markdown | ZIP ou pasta pelo seletor compatível, com grupos e caminhos preservados | Não executa plugins; mídia, arquivos ocultos, caches e metadados são relatados e ignorados |
| Arquivos avulsos | Markdown, texto e ZIP; pasta agrupa arquivos antes do envio | Pasta escolhida é do dispositivo cliente, não um caminho do servidor |
| ChatGPT | Lista JSON com conversas mapping/current_node | Preserva ramo atual, papéis user/assistant, IDs e datas disponíveis; informa anexos, ferramentas e outros ramos omitidos |
| Claude | Lista JSON com chat_messages | Preserva papéis, IDs, datas e partes textuais suportadas; relata omissões |
| Drive/outros serviços | Arquivos baixados/exportados previamente | .gdoc contém link, não documento; não há OAuth recorrente, leitura de links ou conector vivo |

Adaptadores são versionados e reconhecem esquemas específicos. Não exigem login na plataforma de origem. Exportações desconhecidas têm erro explícito; não há promessa de compatibilidade universal. Fonte de assistant permanece registro de uma IA, não declaração confirmada da pessoa.

O seletor de pasta filtra conteúdo não elegível antes de montar o ZIP e informa o que **não foi enviado**. Ao enviar um ZIP pronto, o arquivo inteiro chega à instalação antes do inventário; itens depois ignorados estiveram no staging temporário. Essa diferença aparece antes da transferência.

## Importação retomável e autorizada

Envio em blocos de até 1 MiB, checksum SHA-256 e offset durável permitem selecionar novamente o mesmo arquivo e retomar. Conteúdo em revisão fica no staging privado, fora de documentos, busca e IA. O inventário oferece grupos/pastas, prévia buscável paginada e exceções; não exige checkbox por nota.

Depois da autorização, o índice publica fontes progressivamente em transações com checkpoints. Reinício retoma o trabalho, e repetição de confirmação não duplica fontes. Cancelar interrompe publicação e informa as fontes já importadas; remover/desfazer lote apaga apenas fontes sem outro lote independente. Originais no dispositivo não são modificados.

O relatório separa:

- **Entradas:** diretórios, arquivos elegíveis, ignorados e erros de leitura.
- **Documentos/conversas:** reconhecidos, selecionados, não selecionados, importados, duplicados, indexados e erros.

Um JSON pode gerar muitas conversas. Concluir a seleção não significa cobrir todos os itens da origem. Conteúdo não selecionado, anexos omitidos e formatos desconhecidos continuam explícitos; erros parciais permanecem visíveis em Hoje com acesso à cobertura.

## Quotas e retenção

O novo fluxo usa upload de até **100 MiB**, até **500 MiB de texto elegível**, **1 GiB de expansão total**, **50.000 descritores/documentos por migração** e profundidade 32. Notas e conversas individuais têm limite de 8 MiB; exports JSON em lista são processados progressivamente para não exigir dividir o conjunto ao ultrapassar 8 MiB. Há também quotas por proprietário, verificação de disco, razão de expansão, recusa de ZIP64/multipartes, links simbólicos, criptografia e caminhos inválidos.

Esses limites protegem recursos; não certificam desempenho em todos os volumes. A API informa limites e erros. O endpoint antigo /api/imports preserva seu contrato pequeno para compatibilidade; o onboarding novo usa /api/migrations.

No fluxo novo, staging bruto e textos não aprovados são removidos ao concluir ou cancelar; importações abandonadas expiram após sete dias. Snapshot operacional, inclusive de migração manual, exclui migration-staging por padrão. O banco preserva metadados de jobs, seleção e progresso, sem os textos em revisão desse fluxo. Importações antigas feitas por /api/imports guardavam a revisão no SQLite e esse conteúdo continua nos seus backups até cancelar/concluir aquele lote. Após restauração sem staging, fontes já aprovadas permanecem; transferências/revisões incompletas exigem reenviar a origem em uma nova migração.

Fontes aprovadas, conteúdo, hashes, vínculos de lotes e proveniência estruturada ficam na biblioteca/exportação. Desfazer não apaga cópias anteriores em backups nem respostas históricas. Versões alteradas ficam separadas; não há sincronização contínua ou resolução automática de conflitos.

## Hoje e Conversas

Hoje funciona com zero tarefas: foco confirmado, trechos literais para conferir, fontes de apoio e conversas para continuar. Datas da origem são distintas da importação; sem data original, a interface informa a lacuna. Trechos escolhidos por pistas textuais não confirmam decisão vigente, pendência atual ou prioridade.

Busca usa índice textual local por trechos, com ordenação e diversidade. Não usa embeddings nem IA para importar. Recuperação semântica completa e síntese automática de toda a biblioteca não são prometidas.

Conversas têm escopo fixo: biblioteca autorizada para responder ou área escolhida para propostas. Consultar biblioteca não cria ações em área inferida. Cada pedido pede consentimento para o destino mostrado. **Incluir meu foco e fontes confirmados** é separado de **Incluir Sobre mim e objetivo**; ambos são opcionais. Foco explícito permite recuperar fontes escolhidas mesmo quando seu título usa outras palavras.

Histórico enviado é limitado e reautorizado por pedido. Pausa, remoção, alteração ou mudança de área de fontes exclui turnos que poderiam reintroduzir o material; mudanças de perfil/foco e opt-in revogado também impedem reutilização. Histórico continua visível ao proprietário; excluir uma área não amplia silenciosamente seu escopo. Falhas não são reenviadas automaticamente, e identificador repetido não gera outra chamada.

Organização e personalização assistidas continuam usando fontes escolhidas, evidências literais, limites e aprovação editável. Perfil confirmado pode ser alterado/limpo em Sobre mim. Importar, buscar, confirmar foco e salvar configuração não geram chamada de modelo.

Aceites técnicos e externos estão em [EXPERIENCE-VALIDATION.md](EXPERIENCE-VALIDATION.md) e [EXPERIENCE-PLAN.md](EXPERIENCE-PLAN.md).
