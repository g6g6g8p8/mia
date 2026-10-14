# Mia Demo — piloto independente com 2 a 3 convidados

13/10/2026. Roteiro da distribuição Mac por convite, conforme [MAC-DEMO.md](MAC-DEMO.md), reutilizando o núcleo a12/Apache-2.0. O aplicativo ainda está planejado; não há participantes/resultados reais registrados. O proprietário enviará convites; este documento não envia mensagens.

## Preparar a rodada

Concluir [ROADMAP.md](ROADMAP.md), D1–D7, para os caminhos oferecidos: artefato assinado/notarizado, app com janela própria, instalação local/servidor na interface, contexto útil, convites e atualização testada. [CLEAN-INSTALL.md](CLEAN-INSTALL.md) é procedimento administrativo de desenvolvimento/suporte, não onboarding do participante.

Informar antes do convite as modalidades aprovadas. Cada participante escolhe **local ou servidor** no onboarding; Neste Mac é sugestão inicial, não obrigação. O Linux do proprietário não determina a escolha dos demais. Se a preferência não estiver disponível, registrar bloqueio/não executado e adiar; não forçar mudança nem transferir sucesso entre modalidades.

Mia suporta um proprietário por instalação. Cada participante usa instalação própria, ou instância privada separada com dados, processo, identidade e conexão validados. HTTPS tem rota própria quando oferecido; o túnel privado do app pode ser o acesso Mac escolhido. Não compartilhar biblioteca, chave, sessão ou senha do proprietário. Mac/iPhone no mesmo backend usam a mesma instalação quando o acesso estiver preparado, sem sync offline.

Antes do convite, identificar versão do app/backend, revisão/pacote, arquitetura/OS aprovados e limitações. Apache-2.0 cobre arquivos próprios; preservar avisos. Convite libera download/canal oficial, não senha/dados nem restrição sobre compilar o código. O serviço de convites não controla uso da biblioteca instalada. Ensaio interno acompanhado não conta como piloto independente.

Usar o [rascunho do convite](PILOT-INVITE.md) depois de preparar a opção escolhida. Fontes e credenciais ficam na instalação da pessoa. Não solicitar histórico completo, chave ou acesso ao vault como condição do teste. Modelo é opcional; núcleo sem IA continua sendo cenário válido. O teto anterior de ensaio do proprietário não fornece orçamento aos convidados.

## Sessão de 45–60 minutos

A pessoa recebe pacote/instruções e opera sem intervenção durante a tarefa medida. Pode interromper a qualquer momento. Registrar a necessidade de ajuda antes de oferecer suporte; concluir com ajuda não vira aprovação do requisito independente.

1. **Entrar do zero:** resgatar convite, baixar DMG confiável, mover para Aplicativos e abrir janela própria. Escolher destino, instalar/conectar pelo assistente e criar acesso privado; sem comandos, Git/Python, JSON técnico ou ajuda do fundador. Compreender armazenamento e criar nome/senha/fuso, sem área/chave obrigatória.
2. **Trazer contexto:** escolher vault, arquivos/pasta ou exports suportados próprios; conferir grupos, prévias e cobertura. Autorizar conjunto sem selecionar nota por nota. Registrar itens não enviados, ignorados, perdas e falhas separadamente.
3. **Retomar trabalho:** escolher foco atual e fontes; encontrar um projeto reconhecível, decisão anterior e questão pendente com origem. Abrir o material e conferir autoria/data; registrar tempo até o primeiro resultado que a própria pessoa considera útil. Hoje precisa ser útil sem cadastrar tarefas.
4. **Conversa opcional:** se a pessoa escolheu IA, conferir destino/modelo, limite/custo e contexto antes de autorizar. Continuar conversa; incluir foco e perfil somente quando escolhidos. Conferir fontes e qualidade. Propostas exigem revisão: recusar uma, editar/aprovar outra e repetir confirmação para verificar um efeito.
5. **Controle do contexto:** reimportar material, conferir duplicatas/versões e pausar uma fonte; verificar que novos pedidos não a reintroduzem por histórico. Organização e Sobre mim são sugestões opcionais, com evidência/autoria e aprovação editável.
6. **Continuar depois:** fechar/reabrir a janela e sair/reabrir o app; confirmar serviço/dados e reconexão automática conforme modalidade. Verificar login/suspensão/retomada Mac e boot Linux quando oferecido; não reiniciar servidor compartilhado sem janela combinada.
7. **Atualizar e recuperar:** conferir versão/notas e atualizar pelo app com dados de teste; fonte e conversa devem permanecer. No servidor, identificar versões de cliente/backend e atualização explícita do destino. Criar backup privado externo e restaurar em instalação separada; ensaiar falha/recuperação antes de depender de dados importantes.

Servidor no app Mac pode usar túnel SSH gerido pelo aplicativo. Uma instalação HTTPS existente mantém TLS/cookie Secure e autenticação próprios. Acesso de iPhone/navegador externo exige HTTPS e teste separados; não é requisito do piloto Mac nem resultado do túnel. Local não exige domínio/VPN/servidor. Rede privada é opcional. OS real, iPhone e modelos reais exigem evidência própria, sem extrapolar Chromium/simulador.

## Critérios pré-definidos

Meta: primeiro resultado útil em até dez minutos após acesso à instalação; registrar também tempo total desde o convite e instalação separadamente. Qualidade/reconhecimento são avaliados pela pessoa, não só por contagem/indexação. Resultado interno sintético não substitui fontes próprias de convidados.

A rodada fica elegível para revisão quando duas pessoas (ou pelo menos duas de três) concluem convite/app, instalação, importação/revisão, busca/fonte, retomada, continuidade e atualização sem fundador; quem usa IA entende destino/contexto, custo e aprovação. Recuperação e cada modalidade oferecida têm evidência própria.

Registrar todas as falhas, ajuda e cenários não executados, inclusive a terceira pessoa bloqueada. Uma rodada remota não fecha o aceite local; um usuário que preferiu local não deve ser redirecionado silenciosamente para servidor. Critérios são regras de decisão, não resultados já medidos.

Parar o cenário se houver perda de dados, efeito duplicado, envio não autorizado, exposição de credenciais ou limite excedido. Preservar backup/log minimizado local, criar reprodução sintética, corrigir e repetir o caso. Falhas de usabilidade geram correção/reteste. Economia, custo mensal fixo e compatibilidade universal não serão anunciados a partir de uma amostra pequena.

## Resultados privados e minimizados

Copiar [PILOT-RESULT-TEMPLATE.json](PILOT-RESULT-TEMPLATE.json) para pasta privada fora do Git. Usar códigos P01–P03. null significa não coletado; tarefas usam pass, fail, not_run ou not_applicable. status é pending, completed ou stopped; decisão é pending, retest ou eligible_for_owner_review.

Não registrar títulos/conteúdo de notas, prompts/respostas, nomes/emails, caminhos, endereços privados, chaves, cookies, capturas de segredos ou backups no relatório. Coletar modalidade, versão/artefato, formatos/contagens, tempos, pontos de ajuda, compreensão, qualidade e custo conhecido/estimado/desconhecido. Resultado técnico de catálogo não certifica saldo/ferramentas/qualidade.

Compartilhamento é opcional e depende de consentimento. A pessoa conserva suas fontes; relatos de defeito usam reprodução sintética ou recorte explicitamente autorizado/minimizado. Resultados individuais reais não entram no repositório. A síntese informa denominadores/not_run e é revisada pelos participantes antes de publicação; apagar cópias compartilhadas ao fim da revisão ou revogação do consentimento.
