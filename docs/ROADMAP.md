# Roadmap até o piloto independente

13/10/2026. Objetivo: começar com uma Mia vazia, trazer contexto próprio, retomar trabalho com fontes e manter a instalação disponível sem Terminal aberto. O proprietário escolheu Linux acessado por Mac/iPhone; participantes futuros escolhem local ou servidor.

## Estado atual

A a12 implementa importação retomável por grupos, adaptadores versionados, busca por trechos, foco, conversas, Hoje sem tarefas e serviço de usuário. Passou testes técnicos e corpus sintético; não comprova os aceites reais abaixo. Apache-2.0 foi adotada para arquivos próprios, com avisos de terceiros preservados.

O proprietário autorizou limpeza das instalações **da Mia** no MacBook Air e macserver e escolheu habilitar Desktop Commander. Nesta sessão a ferramenta ainda não está disponível: inventário, limpeza, instalação e aceites nessas máquinas estão pendentes de conexão, sem execução remota alegada. O cloud não substitui essa conexão.

## Ordem de execução e evidência

| Etapa | Trabalho concreto | Resultado para avançar | Estado |
| --- | --- | --- | --- |
| R0 — Conectar e inventariar | Desktop Commander no Mac; confirmar SSH para macserver; identificar diretórios, versão, dados, processo, serviços e containers Mia | Lista verificável das instalações, com o que será preservado e arquivado; sem conteúdo/chaves no relatório | Bloqueada pelo acesso à ferramenta |
| R1 — Limpar com recuperação | Parar somente Mia; preservar backup privado e ensaiar restauração; desativar somente registros Mia; arquivar instalações antigas | Nenhuma Mia antiga iniciando/ocupando destino; dados recuperáveis; outros serviços intactos | Pendente de R0 |
| R2 — Instalação vazia | Instalar revisão fixada em código separado dos dados; validar health, versão e configured=false; ativar serviço de usuário | Jornada do zero acessível; sem perfil, documentos ou configuração pessoal herdados | Pendente de R1 |
| R3 — Contexto real (item 1) | Importar vault e exports escolhidos na instalação; revisar grupos, perdas e proveniência | Cobertura reconciliada, originais intactos, decisões/pendências localizáveis com autoria/data disponíveis | Pendente de R2 |
| R4 — Hoje útil (item 2) | Confirmar trabalho atual e fontes; retomar decisão/questão pendente; IA opcional com prévia e teto | Proprietário reconhece resultado útil; pistas antigas e hipóteses não viram fatos/tarefas automaticamente | Pendente de R3 |
| R5 — Linux/Mac/iPhone (item 3) | Serviço após fechar SSH; linger quando escolhido; HTTPS sem alterar outros serviços; acesso real nos dispositivos; reboot em janela combinada | Login/fontes/conversa persistem; serviço volta após boot; backup externo restaurado | Pendente de R2 e infraestrutura escolhida |
| R6 — Mac local (item 4) | Launcher com runtime/wheels reais por arquitetura, assinatura/notarização, Mac limpo, login/suspensão/retomada e recuperação | Instalação/uso diário sem exigir Python/Git/Terminal ao participante; evidência local própria | Fundação implementada; artefato e aceites reais pendentes |
| R7 — Convidar e observar (item 5) | 2–3 participantes, instalação escolhida, fontes próprias, documentação e relatório minimizado | Primeiro valor sem intervenção do fundador; entendimento de armazenamento/IA, continuidade e recuperação comprovados | Pendente dos caminhos que serão oferecidos |
| R8 — Corrigir e decidir release | Corrigir achados, repetir cenários afetados, revisar artefatos e publicar síntese consentida | Decisão explícita do proprietário baseada em evidência, sem promessa de economia não medida | Pendente de R7 |

R3/R4 e R5 podem avançar após a instalação Linux; R6 avança em paralelo. Um piloto remoto preparado não encerra o aceite Mac local. Se um candidato preferir local e o artefato ainda faltar, registrar esse bloqueio e adiar o cenário local, sem forçar mudança para servidor ou anunciar conclusão de ambos.

## Limpeza e instalação guiada

Seguir [CLEAN-INSTALL.md](CLEAN-INSTALL.md), começando pelo inventário somente leitura. Candidatos conhecidos são pontos de partida, não confirmação de uso atual. Arquivar reversivelmente é o padrão da limpeza; exclusão definitiva só após conferir restauração e início vazio. Preservar vaults, backups, Cabeça, listmonk, Drive, certificados e demais serviços. Não usar limpeza global de Docker nem apagar ambientes encontrados apenas pelo nome.

No servidor, uma instância Mia tem **um proprietário**. O piloto usa uma instalação privada por participante: computador/servidor da pessoa ou instância separada com dados, processo, autenticação e HTTPS próprios. Não distribuir a senha nem o endereço da biblioteca pessoal do proprietário aos beta testers. Não há multiusuário compartilhado implementado.

O convite é preparado em [PILOT-INVITE.md](PILOT-INVITE.md) e enviado pelo proprietário depois de escolher os caminhos realmente prontos. Não pedir históricos completos, credenciais ou backups como condição de participação. Cada pessoa opera sua instalação e escolhe quais resultados minimizados compartilhar.

## Evolução depois do núcleo do piloto

| Trabalho | Benefício | Pré-requisito de aceite |
| --- | --- | --- |
| Reimportação incremental com versões/deltas e remoções revisáveis | Manter contexto atualizado | Mudanças, renomeações, conflitos e revogação sem duplicação/perda |
| Drive recorrente opcional | Atualizar pastas escolhidas sem export manual | OAuth próprio opcional, escopo mínimo, export de arquivos nativos, revogação e teste com origem real |
| Melhor seleção/síntese do foco | Mais relevância ao retomar decisões e questões | Qualidade com fontes autorizadas, orçamento, autoria, datas e lacunas conferidos |
| Cliente iPhone além do navegador | Compartilhar arquivos/notificações conforme demanda | Necessidade observada no piloto; o cliente usa instalação escolhida |
| Sync offline entre instalações | Trabalhar desconectado em mais de um dispositivo | Modelo de conflito, identidade, criptografia/revogação e recuperação antes de anunciar suporte |
| Outros sistemas operacionais | Ampliar instalação local | Artefato e testes próprios; sucesso Mac/Linux não certifica Windows |

## Registro de conclusão

Registrar revisão/artefato, modalidade, checks executados, resultado e bloqueio restante. Os relatórios reais e inventários privados ficam fora do Git; este roadmap guarda estados e sínteses sem dados pessoais. Usar [PILOT.md](PILOT.md) e [PILOT-RESULT-TEMPLATE.json](PILOT-RESULT-TEMPLATE.json). Fonte de evidência técnica: [EXPERIENCE-VALIDATION.md](EXPERIENCE-VALIDATION.md).
