# Roadmap — Mia Demo para Mac, por convite

14/10/2026. A a13 implementa o aplicativo independente para Mac, com convite para a distribuição oficial e instalação própria local ou em servidor no onboarding. A liberação aos convidados depende dos aceites abaixo. O piloto por instalação administrativa/navegador deixa de ser o caminho principal. Contrato em [MAC-DEMO.md](MAC-DEMO.md); implementação e evidência em [MAC-DEMO-IMPLEMENTATION.md](MAC-DEMO-IMPLEMENTATION.md).

## Estado e prioridade

A a13 integra o núcleo de contexto a uma janela SwiftUI/AppKit + WKWebView, instalação local privada, assistente SSH/HTTPS, portal de convites e atualização Sparkle do app. A atualização local do backend usa plano revisado, snapshot e recuperação. Não exige que o participante mantenha um Terminal aberto. Isso é implementação revisada, ainda sem liberação da demonstração: faltam assinatura/notarização, publicação dos canais e aceites em máquinas reais. Apache-2.0 continua aplicada; convite controla nossa distribuição oficial, não o direito de compilar ou redistribuir o código público.

A compilação e os 21 testes Swift passaram em runners macOS 15 arm64 e Intel. Os dois DMGs internos foram gerados e passaram na verificação de integridade. Esses artefatos não assinados não são a distribuição para participantes. Conferir o resultado final do artefato/revisão no PR e CI, sem extrapolar para abertura pelo Gatekeeper, instalação em Mac limpo ou uso diário.

O proprietário trouxe um relato de instalação limpa Linux operacional, ainda sem acesso diário no Mac/iPhone. Esta sessão não verificou o host nem a preservação dos outros serviços/vaults. O log de Desktop Commander comprova execuções em outra sessão; as ferramentas continuam ausentes nesta conversa. Isso não bloqueia planejamento/implementação no repositório, mas é requisito para alegar operações verificadas nas máquinas pessoais.

## Sequência da entrega

| Etapa | Trabalho concreto | Resultado para avançar | Estado |
| --- | --- | --- | --- |
| D0 — Contrato da demo | App como entrada, convite oficial, destino real, primeira utilidade e atualização | Jornada/escopo registrados em MAC-DEMO | Registrado e implementado na a13; aceites de distribuição separados |
| D1 — Janela e artefato Mac | Assinar DMGs por arquitetura com Developer ID, notarizar, conferir tickets/avisos e abrir em Mac limpo | DMG abre janela própria sem dependências/comandos do usuário | Janela/seletores/runtime implementados; Swift aprovado e DMGs internos gerados/verificados em ambas as arquiteturas; distribuição assinada e aceite real pendentes |
| D2 — Instalação local | Ensaiar o assistente, proprietário privado, serviço, reabertura/login/suspensão e recuperação em Mac real | Onboarding dentro do app; serviço/contexto persistem sem Terminal | Controlador, launchd, isolamento e recuperação implementados/testados; aceite de OS/GUI pendente |
| D3 — Meu servidor | Validar SSH, identidade, instalação isolada, túnel/reconexão e boot em Ubuntu 24.04 amd64 preparado; informar pré-requisitos antes do convite | Opção oferecida instala/conecta sem Terminal; persistência e reconexão reais comprovadas | Assistente, companion offline e HTTPS implementados/testados; exige SSH por chave/agente, systemd de usuário e linger já habilitado; aceite SSH/boot real pendente |
| D4 — Contexto e Hoje | Revisar fontes reais, grupos/cobertura, foco e retomada com o proprietário e depois convidados | Pessoa reconhece primeiro valor; perdas/cobertura reconciliadas | Seletores/onboarding fontes → foco → Hoje integrados; fluxos Chromium aprovados, qualidade com fontes próprias pendente |
| D5 — Convites e canal | Publicar o portal em HTTPS com artefato assinado, testar emissão/resgate/revogação/download e preparar links individuais privados | Distribuição oficial por convite; biblioteca instalada independe do portal | Portal/resgate idempotente/expiração/revogação/download retomável implementados/testados; publicação e convites reais pendentes |
| D6 — Atualizar sem recomeçar | Publicar appcast Sparkle e feed de backend autenticados; ensaiar app assinado e atualização local/falha/restauração; definir caminho remoto | Atualizar preserva fontes/conversas; versão/compatibilidade e recuperação são compreensíveis | Sparkle 2.10.0 e atualização local de backend implementados/testados; canal/chaves/ensaio assinado pendentes. Atualização remota de backend pela interface e migração de runtime/bootstrap permanecem abertas |
| D7 — Revisar demonstração | Percurso em Mac limpo e servidor oferecido, fontes reais, continuidade, atualização/restauração externa | Artefato confiável e escolhas realmente prontas; evidência sem dados pessoais no Git | Revisão de código e ensaios sintéticos executados; aceites reais de D1–D6 pendentes para cada caminho oferecido |
| D8 — Rodada e correções | 2–3 convidados, preferência de instalação, teste sem fundador, relatório minimizado, correções/reteste | Próxima atualização baseada em utilidade, autonomia e continuidade observadas | Pendente de D7 |

Próxima sequência: obter assinatura/notarização no Mac de build; executar **DMG → abrir Mia → instalar Neste Mac → importar uma fonte → confirmar foco → Hoje → fechar/reabrir**; verificar login/suspensão e backup/restauração; publicar/testar convites e atualização assinada; aceitar o servidor preparado se oferecido; convidar 2–3 pessoas. A implementação de D3/D5/D6 permite preparar esses ensaios em paralelo. Assinatura/notarização não é substituída por instruções de contorno do Gatekeeper.

Local é a sugestão inicial, não obrigação. Cada opção oferecida precisa de aceite próprio. Não mostrar opção incompleta como pronta, encaminhar silenciosamente a comandos ou forçar modalidade. Informar disponibilidade antes do convite; a demonstração completa mantém os dois caminhos no contrato.

## Operação pessoal e acesso adicional

Inventário, backup verificado, arquivamento reversível e instalação vazia seguem [CLEAN-INSTALL.md](CLEAN-INSTALL.md), como procedimento administrativo de desenvolvimento/suporte. Conferir evidências reais antes de declarar limpeza concluída. Preservar vaults, backups, outros aplicativos, certificados e rotas compartilhadas; sem limpeza global Docker/Python.

Uma instalação tem **um proprietário**. Cada participante usa dados, processo e identidade próprios; não distribuir login/biblioteca do fundador. Convite de distribuição e autenticação da instalação são coisas distintas.

Mac/iPhone podem acessar o mesmo backend com HTTPS preparado/testado. O túnel do app Mac não dá acesso ao iPhone. Essa configuração é opcional para a demo Mac, com evidência própria; não é sync entre bancos ou suporte offline. Reboot de servidor compartilhado exige janela combinada.

## Depois da demonstração

| Trabalho | Benefício | Pré-requisito de aceite |
| --- | --- | --- |
| Servidor mais simples e atualização remota | Reduzir preparação administrativa e manter o backend pela interface | Resolver pré-requisitos não atendidos com consentimento claro; atualização transacional e recuperação em servidor real |
| Relevância, contexto e UX | Retomada com menos configuração | Resultados reais, fontes/permissões e migrações que preservam dados |
| Reimportação incremental/deltas | Manter contexto atualizado | Renomeações, conflitos e revogação sem duplicação/perda |
| Drive recorrente opcional | Atualizar pastas escolhidas | OAuth opcional, escopo mínimo, arquivos nativos e revogação |
| iPhone: HTTPS e cliente nativo conforme demanda | Contexto do destino escolhido em outro dispositivo | Acesso real seguro e necessidade observada |
| Sync offline entre instalações | Trabalhar desconectado em vários dispositivos | Identidade, conflitos, criptografia/revogação e recuperação |
| Mais arquiteturas/OS/servidores | Ampliar instalação própria | Artefatos e aceites próprios; Mac/Ubuntu não certificam outros sistemas |

## Registro e convites

Registrar artefato/revisão, canal, modalidade, tempo desde convite e desde instalação acessível, utilidade, ajuda, atualização e recuperação. Inventários/resultados reais ficam fora do Git. [PILOT.md](PILOT.md), [PILOT-RESULT-TEMPLATE.json](PILOT-RESULT-TEMPLATE.json) e [PILOT-INVITE.md](PILOT-INVITE.md) seguem o novo contrato. O proprietário envia convites; não há disparo automático nem resultados de beta alegados.
