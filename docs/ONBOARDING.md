# Onboarding com conhecimento próprio

Status: plano de implementação aprovado para avanço; funcionalidades abaixo ainda não implementadas. Direção registrada em 11/10/2026 após o primeiro teste do proprietário.

## Problema e resultado esperado

O onboarding atual cria proprietário e primeira área. A pessoa entra em uma central vazia, precisa cadastrar contexto manualmente e ainda não consegue usar suas notas ou conversas. Isso limita a avaliação da proposta de IA pessoal.

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

Compatibilidade com exportações específicas deve ser verificada em documentação oficial e amostras autorizadas antes de implementar os adaptadores. Não assumir um formato universal ou prometer importação de todas as plataformas. Testes usam dados sintéticos; dados reais não entram no repositório.

Não exigir login em plataformas de origem para importar. Não instalar dependências de sincronização ou enviar o arquivo inteiro a uma API de IA automaticamente. A primeira entrega importa uma cópia, sem sincronização contínua com o vault original. PDF, OCR, anexos, links externos e interpretação de plugins do Obsidian ficam para depois.

## Importação, fontes e memória

- Documento importado: conteúdo do usuário com origem, lote, título, caminho relativo, data disponível e hash. Data de importação não substitui data da informação.
- Conversa importada: registro com mensagens e papéis preservados. Resposta antiga de uma IA não vira um fato confirmado, nem instrução para a Mia.
- Índice: derivado, local e reconstruível; aponta para trechos do documento original.
- Perfil, objetivos, projetos e tarefas sugeridos: propostas separadas do conteúdo original, com fontes e confirmação antes de ativar.
- Conteúdo histórico pode estar desatualizado. A pessoa confirma prioridades atuais; a Mia apresenta conflitos ou lacunas em vez de mesclar como verdade.

Uma nota pode existir sem gerar tarefa. Importar uma conversa não executa ações discutidas nela. A organização sugerida por IA será opcional, com consentimento e limites de uso explícitos; a base da importação funciona sem IA e sem internet após instalar.

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

Estados persistidos: recebido, preparando, aguardando revisão, importando, concluído, parcial, falhou, cancelado. Reinício não duplica documentos. Cancelamento ou exclusão do material pendente remove o staging. Lotes concluídos continuam rastreáveis.

Duplicação por conteúdo idêntico não cria novo documento ativo silenciosamente. Mesmo caminho com conteúdo diferente vira conflito para revisão; não sobrescrever a versão anterior sem decisão. Hash igual com metadados diferentes preserva a proveniência do lote quando necessário.

## Uso do conhecimento no harness

Apenas armazenar arquivos não conclui a entrega. Busca e Inteligência precisam recuperar trechos autorizados relacionados à pergunta, dentro da área escolhida e de um limite de contexto. A primeira versão usa busca textual local, sem exigir embeddings ou serviço externo.

Antes do envio ao modelo, mostrar os trechos e seu destino. Na resposta, referências permitem abrir o trecho original. Diferenciar fontes consultadas de fontes citadas; detectar referência inexistente e indicar resposta sem sustentação. Uma conclusão da IA continua sendo interpretação, mesmo quando há fontes válidas.

Excluir ou alterar uma fonte invalida seu índice e remove o conteúdo de novas consultas. Execuções antigas mantêm seu registro como histórico, claramente datado; a interface deve explicar essa diferença.

## Entregas pequenas e aceites

| Fase | Entrega | Aceite |
| --- | --- | --- |
| 1 — Importar e revisar | Markdown/texto/ZIP, lotes, prévia, seleção, fontes e relatório | Instalação vazia recebe fontes reais escolhidas; reimportação/reinício não duplica; falhas são visíveis |
| 2 — Usar fontes | Busca local, trechos autorizados, integração com contexto do M2 e links para evidências | Pessoa encontra uma nota; com modelo configurado, consulta o material e confere a referência original |
| 3 — Onboarding guiado | Fluxo retomável, objetivo declarado, configuração de modelo na interface, primeira consulta e Hoje | Pessoa chega ao primeiro resultado sem cadastrar todo o conteúdo manualmente |
| 4 — Conversas e personalização | Adaptadores ChatGPT/Claude, papéis, seleção e sugestões revisáveis de áreas/perfil | Conversa selecionada é recuperável; mensagem da IA não vira fato; nenhuma tarefa surge sem aprovação |

As fases pertencem ao M3, após o trabalho implementável do M2. A configuração gráfica do modelo deve tratar credenciais no servidor e usar os requisitos de orçamento do M2. Não adiar busca/importação sem IA por falta de chave paga; o aceite com modelo real continua separado.

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
