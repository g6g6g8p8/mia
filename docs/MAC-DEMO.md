# Mia Demo — aplicativo Mac por convite

Direção de 13/10/2026, implementação iniciada em 14/10: aplicativo independente para Mac, por convite, com onboarding que prepara uma instalação própria no computador ou servidor. A demonstração precisa ter qualidade de produto; atualizações ampliam a entrega. A a14 amplia cliente/controladores/distribuição; a referência a13 compilou no Mac e a validação integrada a14 está pendente. Isso ainda não é liberação para convidados. [Estado e evidência](MAC-DEMO-IMPLEMENTATION.md).

## Entrega e mensagem

**“Seu contexto de trabalho, reunido na Mia. Retome projetos, encontre decisões e avance com fontes.”**

A pessoa recebe um convite, baixa a Mia, arrasta para Aplicativos e abre uma janela própria. O app inclui seus componentes. Instalar Git/Python/pacotes, manter Terminal aberto e revisar JSON não fazem parte do percurso principal. A escolha inicial prepara o destino real antes de importar.

A demonstração usa o produto e os dados que continuam nas atualizações. Uma opção futura **Explorar um exemplo** pode usar material sintético identificado, em armazenamento separado; nunca preencher a biblioteca pessoal silenciosamente ou apresentar exemplos como trabalho da pessoa.

## Onboarding dentro do app

| Passo | Pergunta ou ação | Resultado necessário |
| --- | --- | --- |
| Boas-vindas | **Começar** | Versão/canal visíveis; percurso na janela da Mia |
| Destino | **Onde você quer guardar seu contexto?** — **Neste Mac** (recomendado para começar), **No meu servidor**, **Conectar à minha Mia** | Preparar/conectar ao destino escolhido; informar armazenamento antes da transferência |
| Minha instalação | **Esta Mia é sua** — criar acesso ou entrar | Instância privada identificada, nome/senha e fuso; sem identidade ou biblioteca do fundador |
| Fontes | **De onde vem seu trabalho?** | Seletores nativos para Obsidian/pasta, Markdown, exports suportados ChatGPT/Claude e arquivos exportados de outros serviços |
| Cobertura | **Confira o que vai entrar** | Grupos, prévias, contagens/erros reconciliados, confirmação e progresso retomável |
| Retomada | **O que você quer retomar primeiro?** | Foco confirmado e fontes escolhidas; datas/autoria e questões antigas conferíveis |
| Hoje | **Continue de onde parou** | Trabalho reconhecível, decisão anterior e questão pendente com fontes, sem exigir tarefas cadastradas |

O convite identifica a distribuição, não autoriza dados de uma instalação. Área, projeto, chave de IA e preços não bloqueiam a primeira utilidade. Configurar IA entra depois, com destino, contexto e limite claros. Importar e buscar funcionam sem geração.

A navegação permanece **Hoje, Conversas, Biblioteca, Ajustes**. Instalação/conexão, backup e atualização ficam em Ajustes. Caminhos, hashes, portas e comandos ficam nos detalhes técnicos opcionais. Falhas oferecem ações concretas, preservam estado e não anunciam sucesso parcial como conclusão.

## Neste Mac

O instalador contém runtime/dependências verificados por arquitetura. O app cria instalação vazia privada em Application Support, ativa serviço do usuário e abre a interface na sua janela. A ativação explica brevemente o alcance; o plano técnico é inspecionável sem exigir TextEdit/Terminal.

Dados, runtime gerenciado e snapshots ficam fora do bundle em Aplicativos. Atualizar o app não apaga a biblioteca. Fechar a janela mantém o serviço; **Parar Mia** é explícito. Mostrar **“Disponível enquanto este Mac estiver ligado e acordado”**. Login, suspensão e retomada exigem teste real. Acesso pelo iPhone é preparação adicional, não requisito do uso local no Mac.

## No meu servidor

O assistente coleta endereço, usuário e autenticação SSH por agente/chave existente ou seletor. Confirma identidade do host, verifica sistema, arquitetura, espaço/permissões e apresenta mudanças em linguagem comum. Primeira matriz planejada: Ubuntu 24.04 LTS amd64; sua oferta depende do artefato correspondente passar o aceite. Outras combinações ficam indisponíveis com motivo explícito até validação própria.

Instalar artefato verificável em diretório privado novo, com runtime próprio e serviço do usuário. Não substituir Python global, limpar Docker, alterar outros produtos ou herdar contexto antigo. Persistência após logout/boot e mudanças privilegiadas têm revisão de alcance no assistente. Se faltar permissão, pausar e informar o requisito; uma máquina inacessível não vira instalação concluída.

Para a demo Mac, o app pode gerir um **túnel SSH criptografado** até o backend loopback. Conecta/reconecta sem Terminal, domínio ou publicação HTTP. Verifica health, versão, destino e login antes de concluir. Fechar a janela mantém o cliente ativo; sair do app pode encerrar o túnel, mantendo o serviço remoto. Reabrir reconecta. Falha de rede não reinstala nem cria biblioteca vazia. Snapshot, atualização do backend incluído e recuperação de interrupção são ações revisadas no app, vinculadas à identidade e ao estado daquele servidor; aprovações antigas não atravessam troca de destino.

Criar o primeiro proprietário pelo canal privado. iPhone/navegador externo exigem HTTPS persistente posterior, com teste nos dispositivos/rede escolhidos. O túnel Mac não comprova esse acesso. Rede privada existente é opcional; nenhum fornecedor vira requisito do núcleo.

## Conectar à minha Mia

Validar HTTPS, versão e identidade da instância antes do login. O contexto permanece no destino; não copiar automaticamente o banco para o Mac. Conexão SSH existente pode ser oferecida quando suportada e validada, preservando a política de cookies/acesso daquela instalação. Trocar destino identifica a nova instância e exige sua própria sessão.

## Convites oficiais

**Invite only controla o download e o canal oficial da demonstração.** Convite resgata link individual, com prazo e uso único conferidos pelo pequeno serviço de distribuição. Guardar somente o necessário para convite/download, separado das instalações. Telemetria de produto não é obrigatória; notas, históricos, senhas, chaves e endereços de servidores não passam por esse serviço.

O portal externo escolhido é a Vercel gratuita, com metadados duráveis de convite separados do contexto e DMGs em Blob privado. Em 15/10, conta Hobby ativa e stores Blob disponíveis foram conferidos; o kit preparatório está em https://mia-beta-distribution.vercel.app, retornando 503 enquanto o beta não é liberado. Upstash Free vinculado à produção, com PING/EVAL verificados; capacidade dos artefatos finais e ensaio completo continuam pendentes; ver BETA-PUBLICATION.md. Links privados de leitura valem por até 60 segundos; revogar impede novos links, mas uma transferência já iniciada pode terminar.

Depois de instalar, **Abrir a Mia com meu convite** ativa no Keychain uma autorização de até 90 dias para appcast e atualizações oficiais. O núcleo local não depende de consulta periódica ao serviço de convites. Revogação ou expiração encerra novos downloads/atualizações oficiais; não desativa biblioteca, exportação ou recuperação. Convite não substitui autenticação da instância nem exige uma conta global de contexto.

Apache-2.0 permanece no código próprio: compilar/modificar/distribuir o código público não exige convite. Controle refere-se à nossa distribuição/canal e participação na rodada; não promete impedir cópias do código aberto. Voucher apenas offline não garante resgate único. Infraestrutura de distribuição ampliada na a14, com revisão integrada e publicação ainda pendentes; nenhum convite real foi emitido nesta execução.

## Arquitetura e atualização

Implementação a14: **SwiftUI/AppKit + WKWebView**, com janela, menus, seletores e operações nativas, reutilizando backend Python e interface de contexto. Não reescrever importadores/busca/aprovação. Views nativas controlam instalação/conexão; conteúdo web remoto não recebe bridge de execução privilegiada, arquivos livres ou credenciais.

Runtime/wheels macOS reais por arquitetura e OS mínimo comprovado no artefato. Credenciais de acesso do cliente ficam no Keychain/agente autorizado, sem segredos em argumentos/logs; credenciais de IA continuam no destino escolhido sob sua política. Dados pessoais e chaves de distribuição ficam fora dos artefatos/Git.

Túnel com argumentos estruturados, chave do host confirmada, bind loopback e identidade de processo; sem desativar SSH/TLS. WKWebView tem armazenamento de sessão separado por instalação: portas diferentes em localhost não isolam cookies. Conferir origem, uploads e reconexão. Cookie Secure de instância HTTPS não pode ser reduzido automaticamente para permitir túnel HTTP; preservar política ou usar HTTPS.

Atualização aparece no app com versão, notas e **Atualizar**. **Sparkle 2.10.0** substitui o app assinado; o gerenciador transacional atualiza o backend com confirmação separada. Feed/artefatos exigem autenticidade por assinatura; checksum sozinho não autentica origem. Revisar licença/avisos de qualquer componente novo antes de distribuir.

Declarar compatibilidade cliente, bootstrap/gerenciador, runtime e backend. Local: coordenar troca do app/backend, lock, snapshot, health e recuperação em dados novos; não abrir código antigo sobre banco migrado. Remoto: atualizar cliente não atualiza servidor; mostrar as duas versões e atualizar o destino com confirmação/backup próprios. O bootstrap atual não recebe capacidades novas por atualização comum do backend; migrá-lo exige entrega específica. A atualização preserva o runtime privado verificado, mesmo quando uma nova assinatura Apple altera os bytes do runtime incluído no app; exige a mesma proveniência upstream autenticada. Runtime legado sem essa prova não é automaticamente promovido a confiável.

Ensaiar download interrompido, pacote/assinatura inválidos, falha de inicialização, banco migrado e troca interrompida do app. Recuperação precisa funcionar se o novo cliente falhar. Nova release não pede reinstalação vazia ou reimportação geral.

## Base existente e lacunas

| Componente | Evidência atual | Trabalho da demo |
| --- | --- | --- |
| Importação, Biblioteca, foco, Hoje, conversas | Núcleo integrado à janela; Chromium histórico passou, ensaio WKWebView a14 implementado | Execução do ensaio WKWebView a14, fontes próprias e primeiro valor |
| Operação/serviço | Assistente gráfico, planos/recuperação e bootstrap privado implementados/testados | Execução do ensaio launchd a14, login/suspensão, migração de runtime/gerenciador e OS real |
| Cliente/empacotador Mac | a13 compila/testa em arm64/Intel; pipeline a14 inclui ensaios e recibos finais | DMGs aprovados, assinatura/notarização e Mac limpo |
| Servidor | Preflight/instalador/túnel/HTTPS e planos remotos de snapshot/atualização/recuperação implementados; runtime exercitado em isolamento | SSH/systemd/boot reais na matriz preparada; assistente não habilita linger |
| Convites | Portal, metadados duráveis, Keychain e downloads privados implementados; validação integrada a14 pendente | Vercel gratuita: conta/quotas/recursos, publicação HTTPS e emissão real após aceites |
| Atualização do app | Sparkle com appcast privado e atualização local/remota do backend com recuperação implementados | CI a14, chaves/atestação, atualização assinada e operação remota reais |

## Prontidão antes dos convites

1. Mac limpo da arquitetura oferecida: convite, DMG confiável e janela Mia sem Git/Python/Terminal ou fundador. Compilação e testes Mac a13 passaram no CI; a14 precisa concluir o seu; assinatura/notarização, conta Apple Developer, credenciais de distribuição e esse aceite real ainda estão pendentes.
2. Local: criar acesso, importar fonte própria, conferir cobertura e Hoje útil; reabrir/login/suspensão/retomada sem perda. Medir tempo total desde convite e meta separada de primeiro valor em até dez minutos após instalação acessível.
3. Servidor, se oferecido: mesmo percurso pelo assistente, reconexão, fechamento do SSH externo, boot em janela autorizada, isolamento e backup. Local não aprova remoto, nem o inverso.
4. Atualizar pelo app e ensaiar falha/recuperação com dados de teste. Conferir fonte/conversa preservadas; restaurar backup externo em instalação separada.
5. Publicar/testar o portal na Vercel dentro das quotas gratuitas: convite único, resposta perdida, download, ativação no Keychain, atualização privada, expiração e revogação. Conferir que a biblioteca continua operando sem o portal. O publicador exige atestação Apple e registro humano de aceite para o SHA exato e cada arquitetura/modalidade oferecida; não promove DMGs internos apenas por existir um recibo.

Uma demonstração interna anterior pode usar corpus sintético identificado. Para convidados, só mostrar modalidades aprovadas; se servidor faltar, informar antes da distribuição e não declarar o contrato completo entregue.

## Resultado do beta independente

Depois da prontidão, realizar rodada de 2–3 convidados com instâncias próprias/preferência respeitada. Registrar ajuda antes de oferecê-la e cenários não executados; suporte não vira aceite independente. Correções e nova atualização seguem evidência dessa rodada.

Depois da primeira demo: iPhone nativo, sync offline entre bancos, Drive recorrente, hospedagem administrada, instalação automática de modelos e suporte universal. Exportar arquivos do Drive e usar modelo já disponível continuam opções com limites claros.

Sequência em [ROADMAP.md](ROADMAP.md), contexto em [EXPERIENCE-PLAN.md](EXPERIENCE-PLAN.md) e avaliação em [PILOT.md](PILOT.md).
