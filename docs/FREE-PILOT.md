# Piloto gratuito — Mac e navegador

Decisão do proprietário em 17/10/2026: **app Mac distribuído diretamente sem notarização** e **Mia no navegador do Mac/iPhone**. Sem contratar Apple Developer, TestFlight ou infraestrutura paga. Esta decisão substitui a obrigatoriedade de notarização para o piloto nos documentos anteriores; a implementação do publicador ainda precisa ser adaptada.

## Contrato

Manter o aplicativo Mac existente e o serviço sem Terminal aberto. Informar antes do download a ausência de Developer ID/notarização e a possível autorização inicial explícita nas configurações do macOS. Não desativar globalmente o Gatekeeper, remover quarentena automaticamente ou tratar alertas de malware/integridade como autorização normal.

O navegador acessa a instalação de cada participante no próprio Mac ligado/acordado ou servidor. O backend Python não roda no iPhone. Não prometer sincronização offline ou aplicativo iOS nativo. Contexto e credenciais permanecem na instalação; Vercel hospeda somente distribuição. Sem dependência do macserver do fundador, Tailscale ou OpenRouter. APIs de IA são opcionais, sob escolha e orçamento do participante.

## Sequência ativa

| Etapa | Trabalho e aceite | Estado |
| --- | --- | --- |
| G0 — Contrato | Registrar caminhos e orçamento zero | Concluído neste documento |
| G1 — Canal de piloto | Implementar política explícita não notarizada, recibos/rótulos/portal coerentes, mantendo hashes, proveniência e autenticidade. Testar rejeição de artefatos alterados e impedir promoção como notarizado | Pendente; publicador atual exige atestação Apple |
| G2 — Mac real | Baixar pelo navegador preservando quarentena; testar abertura normal autorizada, instalação vazia, fontes/Hoje, reabertura, login/suspensão e restauração. Registrar SHA, arquitetura e macOS | Pendente; CI não substitui aceite |
| G3 — Atualização | Ensaiar substituição manual do app e atualização do backend com snapshot/recuperação, entre duas versões, preservando dados/runtime. Não prometer Sparkle nesta edição antes de validar requisitos | Pendente |
| G4 — Navegador | Validar entrada autorizada na mesma instalação pelo Mac; HTTPS autenticado no Safari do iPhone, certificado válido, sessão, importação, logout e reconexão. Distinguir rede local de acesso remoto | Pendente; túnel SSH do app não fornece acesso ao iPhone |
| G5 — Distribuição | Conferir quotas gratuitas, publicar canal identificado e testar convite/download/revogação com artefatos verificados | Pendente; portal preparatório não é beta liberado |
| G6 — Rodada | 2–3 participantes, instalações próprias, primeiro valor, ajuda necessária e continuidade registrados sem dados pessoais no Git | Após os aceites dos caminhos oferecidos |

Não editar booleanos Apple para passar pelos gates atuais. Preservar o publicador assinado para eventual uso futuro; implementar o piloto explicitamente separado. Assinaturas criptográficas com chaves do projeto não exigem Developer ID; checksum sozinho não comprova autenticidade.

No navegador, preservar proteção do primeiro proprietário e políticas de cookies. Não expor diretamente a porta interna do backend, colocar credenciais em URL ou exigir um fornecedor específico. Tela inicial do iPhone é conveniência adicional, não prova de funcionamento offline.

Oferecer apenas arquiteturas/modalidades aprovadas e informar limitações antes do convite. O proprietário escolhe destinatários e envia; nenhuma emissão ou envio decorre deste documento. Preservar Cabeça, Vaults e outros serviços.

## Evidência já obtida

- Revisão 3499e2c: [CI Python](https://github.com/g6g6g8p8/mia/actions/runs/38908021450), 722 aprovados incluindo Redis real, testes existentes inalterados.
- [CI nativo](https://github.com/g6g6g8p8/mia/actions/runs/38908021850): cinco jobs da última tentativa aprovados. Primeira tentativa Intel falhou por contenção de operation.lock; reexecução aprovada não comprova correção da causa. Investigar em G2/G3.
- DMGs existentes continuam internos até adaptação e aceites. Nenhum build notarizado ou aceite humano é alegado.
- Procedimentos Apple anteriores ficam adiados, preservados como histórico.

## Referências

- [Apple: abertura de apps no Mac](https://support.apple.com/en-us/102445)
- [Apple: conta gratuita](https://developer.apple.com/help/account/basics/about-your-developer-account)
- [Apple: app web no iPhone](https://support.apple.com/en-lamr/guide/iphone/iphea86e5236/ios)

## Preparação implementada — 17/10/2026

`python3 scripts/prepare_free_pilot.py --help` oferece `acceptance-template`,
`verify-mac` e `plan`, sempre com `--dmg`, `--receipt` e `--output` fora do checkout.
`plan` aceita `--acceptance` e `--mac-verification`. Arquivos de saída são novos,
privados e nunca sobrescritos. Não há publicação nem emissão de convite.

O preparador exige recibo original de build sem canal automático e sem afirmações
Apple, vincula bytes/versões/fonte limpa/ensaios nativos e gera aceites inicialmente
`not_run`. `verify-mac` monta somente para leitura, verifica o DMG, arquitetura e
inventários de app/fonte/runtime/wheels, sem executar o app montado. É evidência
técnica do operador, não uma atestação Apple nem aceite humano. O plano permanece
`ready_for_beta=false`, mesmo quando pronto para revisão: autenticação do pacote,
integração com portal e ensaio HTTPS ainda faltam. O publicador Apple mantém seu
comportamento padrão e rejeita esses recibos.

Validação local: 79 testes passaram entre política do piloto, publicador existente
e recibos Mac, com dependências do lock. Fixtures são sintéticas; nenhum aceite
em Mac/iPhone foi inferido. G1 está parcialmente implementado; G2–G6 pendentes.

O comando `stage` foi acrescentado para preparar pacote privado imutável com
assinatura Ed25519 do projeto (sem Apple Developer). Exige `--acceptance`,
`--approve-sha256` igual ao `stage_approve_sha256` do plano, `--public-key`,
`--sparkle-archive` oficial fixado e conta Keychain existente em
`--sparkle-account` (padrão `mia-free-pilot`). Não gera chaves automaticamente.
A ferramenta Sparkle é reutilizada apenas para assinar bytes; isso não habilita
atualização automática do aplicativo. O estágio repete a verificação nativa,
recusa aceites incompletos, chave divergente e destino existente. O manifesto
assinado vincula DMG e evidências; o leitor exige chave pública confiável fornecida
separadamente e recusa qualquer arquivo alterado. Não publica no portal.

Validação ampliada: **89 testes passaram**, incluindo adulteração de cada arquivo
do pacote, chave incorreta, aprovação antiga e preservação de destino existente.
A assinatura nos testes é real Ed25519; artefatos e aceites são sintéticos.

### DMG real verificado no Mac — 17/10/2026

O preparador da revisão `0521bce` executou `verify-mac` com sucesso no Mac arm64
do proprietário, sobre o artefato interno arm64 do workflow `38908021850`
(artefato GitHub `12049271753`, fonte do aplicativo `3499e2c` via merge do CI).
SHA256 do DMG: `da982166c578411912bf452d32205aaf210601e552c08a819dfbb0a865b3ee69`.
Verificados hdiutil, montagem somente leitura, arquitetura, metadados e inventários
reais; o volume temporário foi desmontado pelo verificador. Não executou o app,
não criou instalação/contexto e não alterou serviços existentes.

O download foi pelo gh, portanto **não comprova quarentena ou primeira abertura
pelo navegador/Gatekeeper**. Recibo registra `apple_notarized=false` e
`human_acceptance_verified=false`. Permanecem abertura humana, instalação,
login/suspensão, atualização/restauração, servidor e Safari iPhone. O arquivo é
para ensaio do proprietário, não uma liberação para convidados.

### Falha de primeira abertura e correção — 17/10/2026

O proprietário baixou pelo navegador e copiou para Aplicativos. O macOS exibiu
“Mia is damaged”. Diagnóstico real: `codesign --verify --deep --strict` retornou
`code has no resources but signature indicates they must be present`. O executável
mantinha assinatura `adhoc,linker-signed`, Info.plist não vinculado e nenhum selo
de recursos do bundle. A verificação anterior de hashes não detectava esse defeito.
O DMG `da982166...b3ee69` fica **reprovado para primeira abertura**.

Em cópia separada no Mac, selar o bundle completo com `codesign --force --sign -`
fez a verificação profunda/estrita passar. A quarentena foi preservada; Gatekeeper
continuou retornando `rejected`. Isso comprova correção estrutural da assinatura,
**não** aprovação Apple nem sucesso de primeira abertura pela interface.

O pipeline agora sela o app de desenvolvimento antes dos ensaios, confere o selo
novamente ao emitir recibo e registra `ad_hoc_seal_verified`, sem marcar Developer
ID/notarização como presentes. O preparador do piloto rejeita recibos sem esse
campo e repete a verificação codesign do app montado. 92 testes afetados passaram;
novo build nativo e novo ensaio de download/abertura ainda são necessários.
Nenhum app instalado foi substituído e nenhuma proteção global foi desativada.
