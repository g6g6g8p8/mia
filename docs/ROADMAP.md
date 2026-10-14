# Roadmap — Mia Demo para Mac, por convite

13/10/2026. A próxima entrega é um aplicativo independente para Mac, com convite para a distribuição oficial e instalação própria local ou em servidor preparada no onboarding. O piloto por instalação administrativa/navegador deixa de ser o caminho principal. Contrato, arquitetura e aceites em [MAC-DEMO.md](MAC-DEMO.md).

## Estado e prioridade

A a12 implementa núcleo de contexto, interface web e operações/recuperação. O launcher atual abre o navegador e pede revisão de JSON; não cumpre o contrato de aplicativo. Janela nativa, assistente remoto, DMG assinado/notarizado, convites e atualizador do app estão planejados. Apache-2.0 continua aplicada; convite controla nossa distribuição oficial, não o direito de compilar o código público.

O proprietário trouxe um relato de instalação limpa Linux operacional, ainda sem acesso diário no Mac/iPhone. Esta sessão não verificou o host nem a preservação dos outros serviços/vaults. O log de Desktop Commander comprova execuções em outra sessão; as ferramentas continuam ausentes nesta conversa. Isso não bloqueia planejamento/implementação no repositório, mas é requisito para alegar operações verificadas nas máquinas pessoais.

## Sequência da entrega

| Etapa | Trabalho concreto | Resultado para avançar | Estado |
| --- | --- | --- | --- |
| D0 — Contrato da demo | App como entrada, convite oficial, destino real, primeira utilidade e atualização | Jornada/escopo registrados em MAC-DEMO | Planejamento registrado; app não entregue |
| D1 — Janela e artefato Mac | SwiftUI/AppKit + WKWebView, menus/seletores, runtime/wheels, build por arquitetura e assinatura/notarização | DMG abre janela própria em Mac limpo sem dependências/comandos do usuário | Fundação anterior reutilizável; nova entrega pendente |
| D2 — Instalação local | Assistente cria instalação/serviço privado, acesso, retomada e diagnóstico; plano técnico opcional | Onboarding dentro do app; reabre/login/suspensão sem perda | Pendente de D1 e aceite Mac |
| D3 — Meu servidor | Preflight SSH, identidade do host, artefato Linux, serviço isolado, proprietário pelo canal privado e túnel gerido pelo app; HTTPS existente | Matriz oferecida instala/conecta sem Terminal; reconexão/persistência comprovadas | Assistente não implementado; aceite próprio obrigatório |
| D4 — Contexto e Hoje | Seletores nativos, fontes próprias, grupos/cobertura, foco e fontes; IA opcional depois | Pessoa reconhece primeiro valor; perdas/cobertura reconciliadas | Núcleo a12 disponível; integração/qualidade reais pendentes |
| D5 — Convites e canal | Resgate/download individual com prazo, limite de convidados e registros mínimos; sem conta central de contexto | Só convidados recebem distribuição oficial; biblioteca independe do serviço | Pendente de infraestrutura de distribuição |
| D6 — Atualizar sem recomeçar | Atualizador nativo, feed/pacotes assinados, compatibilidade cliente/bootstrap/runtime/backend e gerenciador transacional | App atualiza preservando fontes/conversas e recupera falhas; servidor tem atualização explícita própria | Operação backend disponível; integração app pendente |
| D7 — Revisar demonstração | Percurso em Mac limpo e servidor oferecido, fontes reais, continuidade, atualização/restauração externa | Artefato confiável e escolhas realmente prontas; evidência sem dados pessoais no Git | Pendente de D1–D6 para caminhos oferecidos |
| D8 — Rodada e correções | 2–3 convidados, preferência de instalação, teste sem fundador, relatório minimizado, correções/reteste | Próxima atualização baseada em utilidade, autonomia e continuidade observadas | Pendente de D7 |

Primeira fatia executável: **DMG → abrir Mia → instalar Neste Mac → importar uma fonte → confirmar foco → Hoje → fechar/reabrir**. D3/D5 podem avançar em paralelo após contratos do cliente; D6 deve existir antes da distribuição para que “depois soltamos atualizações” seja um percurso real. Assinatura/notarização não é substituída por instruções de contorno do Gatekeeper.

Local é a sugestão inicial, não obrigação. Cada opção oferecida precisa de aceite próprio. Não mostrar opção incompleta como pronta, encaminhar silenciosamente a comandos ou forçar modalidade. Informar disponibilidade antes do convite; a demonstração completa mantém os dois caminhos no contrato.

## Operação pessoal e acesso adicional

Inventário, backup verificado, arquivamento reversível e instalação vazia seguem [CLEAN-INSTALL.md](CLEAN-INSTALL.md), como procedimento administrativo de desenvolvimento/suporte. Conferir evidências reais antes de declarar limpeza concluída. Preservar vaults, backups, outros aplicativos, certificados e rotas compartilhadas; sem limpeza global Docker/Python.

Uma instalação tem **um proprietário**. Cada participante usa dados, processo e identidade próprios; não distribuir login/biblioteca do fundador. Convite de distribuição e autenticação da instalação são coisas distintas.

Mac/iPhone podem acessar o mesmo backend com HTTPS preparado/testado. O túnel do app Mac não dá acesso ao iPhone. Essa configuração é opcional para a demo Mac, com evidência própria; não é sync entre bancos ou suporte offline. Reboot de servidor compartilhado exige janela combinada.

## Depois da demonstração

| Trabalho | Benefício | Pré-requisito de aceite |
| --- | --- | --- |
| Relevância, contexto e UX | Retomada com menos configuração | Resultados reais, fontes/permissões e migrações que preservam dados |
| Reimportação incremental/deltas | Manter contexto atualizado | Renomeações, conflitos e revogação sem duplicação/perda |
| Drive recorrente opcional | Atualizar pastas escolhidas | OAuth opcional, escopo mínimo, arquivos nativos e revogação |
| iPhone: HTTPS e cliente nativo conforme demanda | Contexto do destino escolhido em outro dispositivo | Acesso real seguro e necessidade observada |
| Sync offline entre instalações | Trabalhar desconectado em vários dispositivos | Identidade, conflitos, criptografia/revogação e recuperação |
| Mais arquiteturas/OS/servidores | Ampliar instalação própria | Artefatos e aceites próprios; Mac/Ubuntu não certificam outros sistemas |

## Registro e convites

Registrar artefato/revisão, canal, modalidade, tempo desde convite e desde instalação acessível, utilidade, ajuda, atualização e recuperação. Inventários/resultados reais ficam fora do Git. [PILOT.md](PILOT.md), [PILOT-RESULT-TEMPLATE.json](PILOT-RESULT-TEMPLATE.json) e [PILOT-INVITE.md](PILOT-INVITE.md) seguem o novo contrato. O proprietário envia convites; não há disparo automático nem resultados de beta alegados.
