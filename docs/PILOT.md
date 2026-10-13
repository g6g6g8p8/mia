# Piloto independente — 2 a 3 pessoas

13/10/2026. Roteiro após a jornada a12 e adoção de Apache-2.0. Ainda não há participantes nem resultados reais registrados. Convites serão enviados pelo proprietário; este documento não envia mensagens.

## Preparar a rodada

Concluir [ROADMAP.md](ROADMAP.md), R0–R6, para os caminhos que serão oferecidos. O proprietário pediu limpeza da Mia no MacBook Air e macserver e instalação vazia; acesso Desktop Commander/inventário ainda precisam ser conferidos. O protocolo é [CLEAN-INSTALL.md](CLEAN-INSTALL.md).

Perguntar a preferência **local ou servidor** antes de orientar cada participante. O Linux do proprietário não determina a escolha dos demais. Um caminho indisponível fica registrado como bloqueado/não executado; não transferir sucesso do servidor para o aceite Mac local.

Mia suporta um proprietário por instalação. Cada participante usa instalação própria, ou instância privada separada com dados, processo, acesso e HTTPS independentes. Não compartilhar biblioteca, chave, sessão ou senha do proprietário. O acesso Mac/iPhone ao mesmo backend usa a mesma instalação, sem sync offline.

Antes do convite, identificar revisão/pacote, arquitetura, instruções e limitações. Apache-2.0 cobre arquivos próprios; avisos de dependências permanecem no pacote. Código de launcher não equivale a instalador Mac assinado/notarizado pronto. Piloto técnico acompanhado pode identificar problemas antes, mas não conta como instalação independente sem ajuda.

Usar o [rascunho do convite](PILOT-INVITE.md) depois de preparar a opção escolhida. Fontes e credenciais ficam na instalação da pessoa. Não solicitar histórico completo, chave ou acesso ao vault como condição do teste. Modelo é opcional; núcleo sem IA continua sendo cenário válido. O teto anterior de ensaio do proprietário não fornece orçamento aos convidados.

## Sessão de 45–60 minutos

A pessoa recebe pacote/instruções e opera sem intervenção durante a tarefa medida. Pode interromper a qualquer momento. Registrar a necessidade de ajuda antes de oferecer suporte; concluir com ajuda não vira aprovação do requisito independente.

1. **Entrar do zero:** instalar ou conectar à sua instância privada vazia, compreender onde os dados ficam, criar nome/senha/fuso sem área ou chave obrigatória.
2. **Trazer contexto:** escolher vault, arquivos/pasta ou exports suportados próprios; conferir grupos, prévias e cobertura. Autorizar conjunto sem selecionar nota por nota. Registrar itens não enviados, ignorados, perdas e falhas separadamente.
3. **Retomar trabalho:** escolher foco atual e fontes; encontrar um projeto reconhecível, decisão anterior e questão pendente com origem. Abrir o material e conferir autoria/data; registrar tempo até o primeiro resultado que a própria pessoa considera útil. Hoje precisa ser útil sem cadastrar tarefas.
4. **Conversa opcional:** se a pessoa escolheu IA, conferir destino/modelo, limite/custo e contexto antes de autorizar. Continuar conversa; incluir foco e perfil somente quando escolhidos. Conferir fontes e qualidade. Propostas exigem revisão: recusar uma, editar/aprovar outra e repetir confirmação para verificar um efeito.
5. **Controle do contexto:** reimportar material, conferir duplicatas/versões e pausar uma fonte; verificar que novos pedidos não a reintroduzem por histórico. Organização e Sobre mim são sugestões opcionais, com evidência/autoria e aprovação editável.
6. **Continuar depois:** fechar Terminal/navegador ou SSH, voltar e confirmar permanência do serviço e dados. Verificar login/boot Linux e login/suspensão/retomada Mac conforme modalidade; não reiniciar um servidor compartilhado sem janela combinada.
7. **Recuperar:** criar backup privado, guardar cópia externa e restaurar em instalação separada; conferir login/fonte conhecida. Ensaiar atualização/recuperação com dados de teste antes de depender de dados importantes.

Servidor exige endereço HTTPS real e teste nos dispositivos/rede escolhidos. Local no computador não exige domínio, VPN ou servidor. Tailscale é uma alternativa opcional; seu uso não invalida a opção servidor escolhida. Resultados externos, Safari/iPhone físico e modelos reais exigem os testes correspondentes, sem extrapolar Chromium ou simulador.

## Critérios pré-definidos

Meta: primeiro resultado útil em até dez minutos após acesso à instalação, com tempo de instalação registrado separadamente. Qualidade e reconhecimento desse resultado são avaliados pela pessoa; não contar apenas documentos/tempo de indexação como utilidade.

A rodada fica elegível para revisão do proprietário quando duas pessoas (ou pelo menos duas de três) concluem instalação, importação/revisão, busca/fonte, retomada e continuidade sem intervenção do fundador; pessoas que usam IA entendem destino/contexto, custo e aprovação; recuperação e modalidade oferecida têm evidência.

Registrar todas as falhas, ajuda e cenários não executados, inclusive a terceira pessoa bloqueada. Uma rodada remota não fecha o aceite local; um usuário que preferiu local não deve ser redirecionado silenciosamente para servidor. Critérios são regras de decisão, não resultados já medidos.

Parar o cenário se houver perda de dados, efeito duplicado, envio não autorizado, exposição de credenciais ou limite excedido. Preservar backup/log minimizado local, criar reprodução sintética, corrigir e repetir o caso. Falhas de usabilidade geram correção/reteste. Economia, custo mensal fixo e compatibilidade universal não serão anunciados a partir de uma amostra pequena.

## Resultados privados e minimizados

Copiar [PILOT-RESULT-TEMPLATE.json](PILOT-RESULT-TEMPLATE.json) para pasta privada fora do Git. Usar códigos P01–P03. null significa não coletado; tarefas usam pass, fail, not_run ou not_applicable. status é pending, completed ou stopped; decisão é pending, retest ou eligible_for_owner_review.

Não registrar títulos/conteúdo de notas, prompts/respostas, nomes/emails, caminhos, endereços privados, chaves, cookies, capturas de segredos ou backups no relatório. Coletar modalidade, versão/artefato, formatos/contagens, tempos, pontos de ajuda, compreensão, qualidade e custo conhecido/estimado/desconhecido. Resultado técnico de catálogo não certifica saldo/ferramentas/qualidade.

Compartilhamento é opcional e depende de consentimento. A pessoa conserva suas fontes; relatos de defeito usam reprodução sintética ou recorte explicitamente autorizado/minimizado. Resultados individuais reais não entram no repositório. A síntese informa denominadores/not_run e é revisada pelos participantes antes de publicação; apagar cópias compartilhadas ao fim da revisão ou revogação do consentimento.
