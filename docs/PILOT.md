# Piloto — 2 a 3 pessoas

## Revisão do próximo piloto — 13/10/2026

Aplicar o [plano de experiência](EXPERIENCE-PLAN.md), após avaliação 2/10 do proprietário. Antes de orientar, registrar a **preferência de instalação de cada participante**: local ou servidor/conectar à instalação existente. O Linux do proprietário não determina a escolha dos demais. Os resultados e falhas são separados por modalidade; código público ainda depende de decisão de licença para distribuição.

Primeiro valor: reconhecer um projeto/assunto em andamento, reencontrar decisão com fonte e revisar uma pendência, sem cadastrar toda a organização para preencher Hoje. O onboarding deve importar vault/exports suportados em grupos e relatar cobertura, sem exigir que a pessoa divida arquivos para vencer o limite atual.

Local: instalação sem comandos no caminho básico, fechar Terminal, reiniciar sessão, suspensão/retomada e preservar dados. Servidor: fechar SSH, reiniciar serviço/host, testar HTTPS no Mac/iPhone e acesso externo quando escolhido. Local no próprio computador não exige domínio, VPN ou servidor. Cliente no iPhone conectado ao mesmo backend não comprova sync offline.

Selecionar participantes para observar ambos os caminhos quando houver preferência real, sem forçar uma modalidade por conveniência do mantenedor. Onde faltar artefato/infraestrutura, registrar aquele cenário como não executado, sem transferir sucesso da outra modalidade. Não convidar pessoas automaticamente nem coletar vaults/chaves no repositório.

O roteiro histórico abaixo continua útil para controles do núcleo, mas não basta para declarar o novo piloto pronto. O template atual pode registrar modalidade/ajuda; será ampliado com cobertura da migração e retomada antes do ensaio redesenhado.

Status: roteiro preparado. O proprietário realizou testes iniciais no celular e identificou lacuna de onboarding/importação. Piloto com usuários externos ainda não concluído.

Objetivo: verificar instalação e primeira utilidade com **2–3 pessoas**, cada uma em uma instalação própria no Mac ou Ubuntu e com fontes escolhidas por ela. O responsável prepara o pacote identificado e estas instruções; o convite e a decisão de compartilhar resultados são explícitos. Não há participantes ou resultados registrados neste documento.

## Antes de convidar

- Validar um provedor/modelo real com chave e teto de gasto autorizados.
- Conferir resposta com fonte, pedido ambíguo, data relativa, proposta inválida, falha de rede e orçamento de uso.
- Definir licença de uso e distribuição; repositório já público por decisão do proprietário.
- Importação básica e recuperação de fontes do M3 disponíveis (`ONBOARDING.md`). Cada participante escolhe dados próprios na instalação sob seu controle. A validação não depende de histórico do desenvolvedor.
- Explicar limitações, tratamento de dados e que a versão não deve guardar informação crítica sem backup.
- Usar pacote/commit identificado, checksum e [avisos](DEPENDENCIES.md) revisados. A licença específica depende do titular: [opções](LICENSE-OPTIONS.md).
- Separar o núcleo sem IA dos aceites externos. Falta de chave, export real ou rota HTTPS não equivale a teste aprovado; marcar `not_run` e continuar tarefas locais possíveis.

## Sessão curta e critérios definidos antes de começar

Reserve cerca de 45–60 minutos para o primeiro uso. A instalação usa somente README/documentação. Registre ajuda quando necessária e deixe a pessoa operar as próprias fontes e credenciais, sem compartilhamento de tela de segredos. Mac e Ubuntu são os alvos; registrar cada ambiente efetivamente testado, sem extrapolar para outros.

1. **Núcleo local:** acesso vazio → área → importação/prévia/seleção → busca → abrir a fonte certa → exportação. Medir tempo até o primeiro resultado que a própria pessoa considera útil.
2. **Revisão:** reimportar uma nota alterada, comparar versões, pausar/reativar; com IA disponível, revisar organização/contexto pessoal e aprovar apenas parte. Conferir que o contexto pessoal não é enviado sem seleção.
3. **IA autorizada:** cada pessoa escolhe destino/modelo e seus limites, confere a prévia e faz uma consulta com fonte. Recusar uma proposta, editar/aprovar outra, confirmar novamente e verificar um único efeito. O teste de catálogo não substitui geração com provedor direto; resultado simulado não fecha qualidade.
4. **Operação:** reiniciar, verificar persistência, criar backup e restaurar em instalação separada. Ensaiar atualização/recovery com dados de teste e backup verificável antes de usar dados importantes.
5. **Independência:** verificar outro dispositivo na LAN sem VPN obrigatória; HTTPS remoto somente com rota/destino controlados pelo participante e autorização específica. Registrar ações fora da Mia, sem alterar rede real só para preencher o roteiro.

O núcleo local pode ser concluído sem chamada paga. Chaves e conteúdo permanecem na instalação da pessoa. O teto já autorizado de US$ 1 para ensaios do proprietário é acumulado e não fornece orçamento automático aos participantes. Para comparar qualidade/custo, usar [BENCHMARK.md](BENCHMARK.md), registrar a configuração e avaliar qualidade antes de calcular diferença. Custo sem evidência é desconhecido; não publicar promessa de economia.

Critérios de sucesso da rodada: as 2 pessoas (ou pelo menos 2 das 3) concluem instalação, importação, busca/fonte e reinício usando a documentação sem intervenção do fundador; todas as pessoas que fazem IA entendem destino/contexto e revisão antes do efeito; nenhum caso de segurança abaixo fica aberto. Ajuda, tempo e a terceira pessoa bloqueada permanecem no relatório e exigem correção/reteste dos pontos aplicáveis. Esses critérios são uma regra de decisão do piloto, não resultados medidos. Aceites de exports reais, provedor direto e HTTPS exigem os testes correspondentes; falta de execução mantém o marco pendente.

**Parada imediata:** perda de dados, efeito duplicado, envio não autorizado de contexto/destino, credencial exposta ou limite configurado excedido. Suspender o cenário, conservar backup/log local minimizado e abrir reprodução sintética; corrigir e repetir o caso antes de avançar ao release. Falha de usabilidade sem impacto em dados pode ser registrada e testada novamente. Decisão de release cabe ao titular depois de revisar os resultados e pendências.

## Tarefas do piloto

1. Instalar usando só o README e criar o acesso local.
2. Criar uma área e uma tarefa real, sem importar histórico do desenvolvedor.
3. Encontrar a tarefa na busca e exportar os dados.
4. Configurar um modelo próprio; conferir destino e contexto antes de enviar.
5. Pedir uma análise da área e conferir se ela se sustenta nos dados disponíveis.
6. Solicitar uma tarefa, revisar a proposta, recusar uma e confirmar outra.
7. Reiniciar a Mia e confirmar a permanência dos dados.

Acrescentar ao fluxo: importar um conjunto pequeno de notas próprias, revisar a seleção, encontrar uma informação, abrir a fonte, consultar esse material com modelo configurado e conferir uma referência. Reimportar uma nota alterada, comparar o original e pausar uma versão; confirmar que ela sai da busca sem ser apagada. Registrar o tempo até o primeiro resultado útil, a necessidade de ajuda e se a pessoa entende o que foi enviado ao provedor.

Para exportações experimentais ChatGPT/Claude, cada participante pode validar o próprio arquivo localmente e informar formato, contagens, erros e resultado. Não pedir upload de históricos completos para o repositório ou para o desenvolvedor. Um relato de problema deve usar reprodução sintética ou trecho explicitamente autorizado e minimizado. Marcar compatibilidade como não validada até existir teste real; isso não bloqueia o piloto de notas e busca sem IA.

## Registrar, sem inventar métricas

Copie [PILOT-RESULT-TEMPLATE.json](PILOT-RESULT-TEMPLATE.json) para um diretório privado **fora do checkout**, por exemplo `~/mia-pilot-results/`, e use códigos `P01`–`P03`, sem nome/email/contato. O template é vazio: `null` significa não coletado, `not_run` significa não executado. Nos resultados de tarefas use `pass`, `fail`, `not_run` ou `not_applicable`; uma dependência indisponível é `not_run`, com categoria de bloqueio. `status` passa a `completed` ou `stopped`; `release_decision` é `pending`, `retest` ou `eligible_for_owner_review`, nunca publicação automática.

Não inserir títulos/conteúdo de notas, conversas, prompts/respostas, caminhos de arquivos, endereços privados, chaves, cookies, capturas de tela ou backup no relatório. Registre formatos/contagens, IDs de tarefas do template, tempos, entendimento, custo conhecido/estimado/desconhecido e um ID de issue já sanitizada quando necessário. O campo de modelo é opcional e somente identificador público; destino é classificado como direto/compatível/local, sem URL privada. O participante mantém as fontes e só compartilha este relatório minimizado com consentimento. Não subir resultados individuais reais ao repositório; publicar apenas síntese revisada, consentida e sem identificação. Apagar cópias compartilhadas quando a revisão terminar ou quando a pessoa retirar a autorização.

Consolidação: quantidade de participantes por OS/método, quantos terminaram cada tarefa, quantos precisaram de ajuda, tempos observados e número de casos interrompidos. Identificar denominadores e `not_run`; nenhum campo ausente vira zero, falha vira aprovação ou amostra pequena vira alegação geral. Os participantes conferem a síntese antes de publicação.

Modelo de relatório por participante (sem dados pessoais): versão/OS; instalou sem ajuda (sim/não e ponto de bloqueio); tipo de fonte escolhida; tempo até primeiro resultado útil; encontrou e abriu a fonte correta; entendeu aprovação e envio ao provedor; reinício/restauração conferidos; custo conhecido/estimado/desconhecido; erro reproduzível minimizado; decisão de continuar. Não coletar o conteúdo da fonte ou a chave. Critérios sintéticos de qualidade/custo estão em [BENCHMARK.md](BENCHMARK.md).

No ensaio de organização, selecionar poucas fontes próprias, conferir a prévia, gerar sugestões, editar um nome/descrição, recusar ou confirmar parte da proposta e verificar o destino das fontes. Reabrir a proposta após reload e editar a área já criada. Registrar se os trechos iniciais bastaram para sugestões úteis; não atribuir ao teste simulado qualidade de um modelo real.

Em Meu contexto, gerar uma sugestão, conferir trechos e autoria, editar e aprovar apenas um campo. Verificar se o objetivo aprovado aparece em Hoje e se o contexto pessoal fica fora da prévia de Inteligência até ser marcado. Editar/limpar o contexto e confirmar que execuções anteriores continuam como histórico. Registrar falsas atribuições ao usuário, material antigo tratado como atual e se a pessoa entende a substituição do objetivo.

Tempo por tarefa, pontos de ajuda, erros, entendimento de confirmação e custos, qualidade da resposta, configuração usada e decisão de continuar ou não. Não coletar chaves, conteúdos pessoais ou telemetria sem consentimento. Usar os achados para corrigir o produto antes de divulgar promessas de economia.
