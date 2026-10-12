# Onboarding com conhecimento próprio

Status: M3 ampliado em 11/10/2026. Objetivo declarado, fluxo retomável, importação revisável, fontes, busca, configuração gráfica de IA, organização assistida em áreas e sugestões revisáveis de contexto pessoal/objetivo disponíveis. Projetos estruturados, sincronização contínua e compatibilidade ampla de exportações continuam planejadas. Qualidade das sugestões com modelos reais ainda não validada.

## Problema e resultado esperado

O onboarding anterior criava proprietário e primeira área. A lacuna de conhecimento próprio motivou o fluxo atual.

Resultado esperado: a pessoa traz um conjunto de conhecimento próprio, entende o que foi aceito e conclui uma primeira consulta com fontes ou uma ação confirmada. A instalação continua vazia por padrão; o preenchimento ocorre por importação explícita ou pelas respostas da própria pessoa.

## Fluxo proposto

| Etapa | Experiência | Resultado persistido |
| --- | --- | --- |
| 1. Acesso | Nome, senha e fuso; informações opcionais não bloqueiam | Proprietário e sessão |
| 2. Primeiro objetivo | “Em que você quer ajuda primeiro?”; resposta curta, editável | Objetivo declarado, sem inferência automática |
| 3. Conhecimento | Importar notas/vault, escolher exportação de conversas, colar conteúdo ou continuar sem importar | Escolha e lote de importação local |
| 4. Revisão | Mostrar documentos, prévias, exclusões, erros e possíveis duplicatas; selecionar e confirmar | Fontes autorizadas e área escolhida |
| 5. Inteligência | Configurar modelo próprio ou continuar com busca local; mostrar destino dos dados | Configuração local e permissão de uso |
| 6. Primeiro resultado | Encontrar informação nas fontes; com IA configurada, responder uma pergunta com referências | Consulta verificável e eventual proposta |
| 7. Entrada em Hoje | Mostrar fontes adicionadas, objetivo declarado e tarefas realmente confirmadas | Estado inicial útil, sem tarefas inventadas |

Todas as etapas podem ser retomadas; o onboarding também pode ser reaberto para adicionar fontes. A pessoa pode revisar uma importação depois de começar a usar. No celular, importar por seletor de arquivos; escolher uma pasta do servidor pertence a uma função administrativa posterior.

## Ordem dos formatos

| Entrega | Entrada | Escopo |
| --- | --- | --- |
| A — Base aberta | Markdown e texto, individualmente ou em ZIP | Notas e vaults com estrutura de pastas preservada; colagem de texto como alternativa |
| B — ChatGPT | Arquivo exportado pelo próprio usuário | Adaptador com formatos reconhecidos, prévia e seleção de conversas |
| C — Claude | Arquivo exportado pelo próprio usuário | Adaptador com formatos reconhecidos, prévia e seleção de conversas |
| D — Outros | Novos formatos/exportações e documentos | Priorizar conforme pilotos; formatos desconhecidos têm erro claro e alternativa de texto |

Adaptadores experimentais reconhecem listas JSON com `mapping`/`current_node` (ChatGPT) ou `chat_messages` (Claude). A árvore é percorrida apenas pelo ramo atual; usuário e assistente mantêm papel e data disponível no texto. Arquivos de conta e conversas sem estrutura reconhecível recebem erro explícito. Páginas oficiais de exportação foram consultadas, mas não estabelecem um esquema estável; compatibilidade exige amostras reais autorizadas. Testes usam dados sintéticos, sem prometer importação universal.

Não exigir login em plataformas de origem para importar. Não instalar dependências de sincronização ou enviar o arquivo inteiro a uma API de IA automaticamente. A primeira entrega importa uma cópia, sem sincronização contínua com o vault original. PDF, OCR, anexos, links externos e interpretação de plugins do Obsidian ficam para depois.

## Importação, fontes e memória

- Documento importado: conteúdo do usuário com origem, lote, título, caminho relativo, data disponível e hash. Data de importação não substitui data da informação.
- Conversa importada: registro com mensagens e papéis preservados. Resposta antiga de uma IA não vira um fato confirmado, nem instrução para a Mia.
- Índice: derivado, local e reconstruível; aponta para trechos do documento original.
- Perfil, objetivos, projetos e tarefas sugeridos: propostas separadas do conteúdo original, com fontes e confirmação antes de ativar.
- Conteúdo histórico pode estar desatualizado. A pessoa confirma prioridades atuais; a Mia apresenta conflitos ou lacunas em vez de mesclar como verdade.

Uma nota pode existir sem gerar tarefa. Importar uma conversa não executa ações discutidas nela. A organização sugerida por IA é opcional, com consentimento e limites de uso explícitos; a base da importação funciona sem IA e sem internet após instalar.

Na última etapa do onboarding e em Fontes, **Organizar minhas fontes** permite selecionar até seis fontes ativas de uma área, ver os trechos enviados e solicitar até quatro áreas sugeridas. A pessoa edita nome/descrição, escolhe áreas e documentos e confirma. Só então áreas são criadas e documentos movidos; os demais permanecem no lugar. Não mescla áreas existentes, não cria tarefas e não altera o objetivo declarado. Detalhes de escopo, custo, confirmação e histórico em `AI.md`. Descrições aprovadas são editáveis depois em Áreas e permanecem mesmo se a fonte original for pausada ou excluída.

**Personalizar minha Mia**, no onboarding/Fontes, abre **Meu contexto**, também acessível em Sistema. A geração opcional propõe um resumo do contexto de trabalho/interesses e/ou um objetivo para revisão, usando até seis fontes explicitamente selecionadas. Trechos literais são obrigatórios; o servidor verifica sua presença no material enviado, não a interpretação ou autoria das afirmações. O usuário deve conferir se o conteúdo se refere a ele e continua atual. Respostas antigas de assistentes não são evidência automática sobre o usuário.

Contexto e objetivo são editáveis, selecionados e confirmados separadamente. Confirmar o objetivo substitui o objetivo atual exibido em Hoje; não cria tarefas nem modifica áreas. Edições mais recentes bloqueiam a substituição por proposta antiga. Fontes usadas precisam continuar ativas e na mesma área até a aprovação. Após a confirmação, o contexto torna-se uma declaração revisada pelo usuário, independente da fonte original; pode ser editado ou limpo em Meu contexto. Execuções antigas preservam seu registro. Em Inteligência, o contexto pessoal e objetivo só são enviados mediante a opção explícita de incluí-los em cada pedido.

## Contrato mínimo da importação

1. Autenticar proprietário e receber arquivo ou texto com limites de tamanho.
2. Armazenar temporariamente dentro da instalação, separado do código e de fontes ativas.
3. Identificar formato; validar ZIP, caminhos e tipos sem executar arquivos ou seguir links.
4. Preparar prévia local, contagens, erros, exclusões e candidatos a duplicação.
5. Receber a seleção e a área de destino autorizada.
6. Confirmar uma única vez, persistir documentos e construir índice de busca local.
7. Apresentar relatório: importado, ignorado, duplicado e falhou; nunca declarar sucesso silencioso com conteúdo perdido.
8. Permitir excluir um lote; remover seus documentos, índices e elegibilidade para novos contextos, preservando documentos independentes de outros lotes.

Limites iniciais de tamanho total, número de arquivos, profundidade, expansão do ZIP e tempo devem ser definidos e exibidos antes do upload. Rejeitar caminhos absolutos, travessia de diretórios, links simbólicos e arquivos fora do escopo. Conteúdo não autorizado não chega à busca nem ao contexto.

Estados atuais: revisão e concluído, com relatório de erros/exclusões por entrada. Parsing é síncrono e limitado; erro antes da preparação não cria lote. Confirmação é transacional. Reinício não duplica documentos; cancelamento/exclusão remove o staging. Jobs em segundo plano ficam para evolução posterior.

Conteúdo idêntico na mesma área é deduplicado, preservando proveniência de lotes e o estado ativo/pausado da fonte existente. Exclusão não remove documento compartilhado por outro lote. A revisão mostra conteúdo já importado e notas com o mesmo caminho e conteúdo diferente, permitindo abrir o original para comparar. Não detecta versões de conversas por posição na exportação, pois essa posição não é um identificador estável.

Versões diferentes permanecem separadas. Na lista de fontes, o usuário pode pausar versões antigas e reativá-las depois. Pausa preserva conteúdo, índice, proveniência e exportação, mas exclui a fonte de busca e de novos contextos. Nenhuma versão é selecionada automaticamente; ambas ficam ativas até a escolha do usuário. Execuções anteriores preservam o contexto registrado. A detecção usa caminhos da mesma área, não interpreta equivalência semântica nem acompanha renomeações.

## Uso do conhecimento no harness

Apenas armazenar arquivos não conclui a entrega. Busca e Inteligência precisam recuperar trechos autorizados relacionados à pergunta, dentro da área escolhida e de um limite de contexto. A primeira versão usa busca textual local, sem exigir embeddings ou serviço externo.

A prévia considera a área e o pedido. Busca e histórico permitem abrir a fonte; o servidor identifica referências válidas/inexistentes e a interface informa as inexistentes. Isso verifica IDs, não a sustentação de cada frase. A consulta atual usa até três trechos de 1.200 caracteres por correspondência textual normalizada, sem embeddings. Qualidade das citações com modelo real permanece pendente.

Excluir ou alterar uma fonte invalida seu índice e remove o conteúdo de novas consultas. Execuções antigas mantêm seu registro como histórico, claramente datado; a interface deve explicar essa diferença.

## Entregas pequenas e aceites

| Fase | Entrega | Aceite |
| --- | --- | --- |
| 1 — Importar e revisar | Markdown/texto/ZIP, lotes, prévia, seleção, fontes e relatório | Instalação vazia recebe fontes reais escolhidas; reimportação/reinício não duplica; falhas são visíveis |
| 2 — Usar fontes | Busca local, trechos autorizados, integração com contexto do M2 e links para evidências | Pessoa encontra uma nota; com modelo configurado, consulta o material e confere a referência original |
| 3 — Onboarding guiado | Fluxo retomável, objetivo declarado, configuração de modelo na interface, primeira consulta e Hoje | Pessoa chega ao primeiro resultado sem cadastrar todo o conteúdo manualmente |
| 4 — Conversas e personalização | Adaptadores ChatGPT/Claude, papéis, seleção e sugestões revisáveis de áreas/perfil | Conversa selecionada é recuperável; mensagem da IA não vira fato; nenhuma tarefa surge sem aprovação |

As fases pertencem ao M3, após o trabalho implementável do M2. A configuração gráfica do modelo deve tratar credenciais no servidor e usar os requisitos de orçamento do M2. Não adiar busca/importação sem IA por falta de chave paga; o aceite com modelo real continua separado.

Limites atuais: upload 8 MB (12 MB em JSON codificado), ZIP expandido 20 MB, até 300 entradas e 500 documentos, até 200.000 caracteres por documento e três lotes em revisão. Sem extração do ZIP no sistema. Há colagem de texto; documentos só ficam ativos após seleção explícita. PDF, mídia e anexos são ignorados e informados no relatório.

## Testes relevantes

- Fluxo no celular: arquivo → prévia → seleção → importação → busca → abrir fonte.
- ZIP inválido, caminho malicioso, arquivo não suportado, conteúdo grande e lote parcialmente legível.
- Repetir importação/confirmar; interromper e reiniciar; cancelar; excluir lote.
- Isolamento por proprietário/área e exclusão propagada para busca/contexto.
- Fonte contendo instrução maliciosa não modifica permissões ou executa ferramenta.
- Uma conversa com respostas de IA permanece distinguível de afirmações do usuário.
- Primeira consulta útil com e sem modelo configurado; dados privados nunca aparecem no Git.

## Exemplo da experiência

A pessoa importa notas de um projeto, seleciona três documentos e escolhe uma área. A Mia informa o que entrou e permite buscar um prazo. Com IA configurada, ela pergunta quais decisões continuam em aberto; a resposta referencia trechos selecionados e informa lacunas. Se pedir uma tarefa, a Mia apresenta a proposta e espera confirmação. A experiência começa com conhecimento do próprio usuário, sem fabricar conteúdo para preencher a tela.
