> **Atualização de escopo — 17/10/2026:** o proprietário escolheu piloto gratuito com app Mac sem notarização e acesso pelo navegador no Mac/iPhone. O contrato vigente e os aceites estão em [FREE-PILOT.md](FREE-PILOT.md). As exigências Apple descritas abaixo pertencem ao canal assinado anterior, adiado. O código do publicador ainda impõe essas exigências; este registro não o adapta nem libera os DMGs internos para convidados.

# Publicação privada do beta Mac

15/10/2026. Este procedimento é do responsável pela distribuição. O convidado
baixa o app, abre seu convite na Mia e escolhe instalar no próprio Mac ou em seu
servidor. Ele não executa estes comandos.

## Estado e recursos

O código prepara uma publicação imutável, um portal Vercel, convites duráveis e
atualizações privadas. **Kit preparatório publicado em 15/10/2026; beta ainda indisponível.**
Origem: https://mia-beta-distribution.vercel.app. Não há convite real emitido.
Evidências e pendências da conta estão no registro ao final deste documento. A conta Apple Developer, o build assinado/notarizado e os
aceites nos aparelhos finais permanecem pendentes. Um DMG interno sem assinatura
não pode ser promovido apenas por editar campos de um recibo.

A Vercel hospeda somente distribuição e metadados de convite. Vaults,
conversas, provedores de IA e bibliotecas pessoais ficam na instalação de cada
participante. A licença do código próprio é Apache-2.0; compilar o código aberto
não exige convite. O controle cobre nossa distribuição oficial e a rodada beta.

Antes de provisionar, conferir na conta conectada:

- Elegibilidade do projeto ao **Hobby gratuito** e quotas atuais. Não habilitar
  Pro, cobrança adicional, upgrade automático ou integração paga.
- Projeto com origem HTTPS estável, podendo usar o domínio gratuito
  `nome-do-projeto.vercel.app`. A origem entra no app antes da assinatura;
  trocar origem ou chaves depois exige migração explícita.
- Um store **Blob privado** para todos os DMGs oficiais e outro **Blob público**
  para os pacotes de código-fonte/dependências do backend. Conferir capacidade
  disponível para os arquivos atuais, os históricos e o tráfego do piloto.
- Integração **Upstash Redis gratuita**, com REST e persistência. Não usar
  SQLite em `/tmp`, memória de uma Function ou um Redis descartável como estado.
- Variáveis de produção vinculadas com a ferramenta da conta, sem exibir valores:
  `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`,
  `BLOB_READ_WRITE_TOKEN` do store privado e `BLOB_STORE_ID`.
  O upload do operador também usa `MIA_PUBLIC_BLOB_READ_WRITE_TOKEN` do store
  público. Esse token público de escrita não precisa ir para a Function.

Os limites gratuitos dependem da conta e do uso; o código não promete custo
mensal fixo nem autoriza contratar capacidade paga. Se o recurso gratuito não
estiver disponível, pausar a publicação e registrar o impedimento.

## Preparar um projeto revisável

Executar no checkout revisado com Python 3.12+ e dependências fixadas. Manter
planos, chaves, recibos, artefatos, convites e kits fora do checkout, em diretório
privado. Os argumentos abaixo são exemplos de nomes públicos; não representam
um domínio reservado ou projeto criado.

```bash
mkdir -m 700 "$HOME/mia-release-work"
python3 scripts/deploy_demo_distribution.py plan \
  --domain nome-do-projeto.vercel.app --project-name nome-do-projeto \
  --output "$HOME/mia-release-work/preparation-plan.json"
python3 scripts/deploy_demo_distribution.py kit \
  --plan "$HOME/mia-release-work/preparation-plan.json" \
  --output "$HOME/mia-release-work/preparation-kit"
```

O kit contém `api/index.py`, `vercel.json`, Python/dependências fixadas e os
avisos originais. Não contém segredos nem DMGs. Sem release aprovado, as consultas GET ao app retornam **503**, com `ready_for_beta=false`. Isso permite
preparar o projeto antes da conta Apple sem anunciar um beta disponível.

Usar a Vercel conectada para revisar conta/plano, criar ou selecionar o projeto
e publicar o diretório do kit, preservando sua configuração. O gerador não
autentica contas nem executa um deploy escondido. Não configurar o repositório
Mia inteiro como portal: o projeto de distribuição recebe o kit separado.

## Assinatura, fonte e aceite

Primeiro gerar os canais por arquitetura com as **chaves públicas reais** do
backend e Sparkle e a origem de produção já escolhida:

```bash
python3 scripts/publish_demo_release.py channels \
  --origin https://nome-do-projeto.vercel.app \
  --backend-public-key "$MIA_BACKEND_PUBLIC_KEY" \
  --sparkle-public-key "$MIA_SPARKLE_PUBLIC_KEY" \
  --output "$HOME/mia-release-work/channels"
```

As duas variáveis deste exemplo contêm somente chaves públicas Base64. Chaves
privadas e credenciais Apple ficam no Keychain ou em arquivo privado fora do
checkout; nunca no chat, argumentos de chave privada ou arquivos versionados.
Usar contas separadas para assinatura do app/Sparkle, feed do backend e atestação
do build. O signatário precisa da ferramenta oficial Sparkle 2.10.0 fixada em
`mia/release_publication.py`; arquivos com outro hash são recusados.

Construir em Mac da arquitetura oferecida, a partir de commit limpo, com canal
revisado, Developer ID Application e perfil notarytool existentes. O procedimento
está em [MAC-DEMO-IMPLEMENTATION.md](MAC-DEMO-IMPLEMENTATION.md). Não usar
`--unsigned` como distribuição de convidados. O recibo formato 2 registra
inventários do app/fonte/wheels, versão, SHA256 do DMG e ensaios nativos.

`publish_demo_release.py attest-mac --help` mostra a etapa que monta o DMG
somente para leitura, repete verificações Apple/Gatekeeper/tickets e confere os
inventários finais antes de assinar a atestação. A publicação verifica essa
assinatura contra a chave pública de build explicitamente revisada. Booleanos
autodeclarados em JSON não substituem a atestação.

Gerar `acceptance-template` com os DMGs e recibos finais, conforme `--help`.
Cada cenário começa `not_run`; preencher evidência, data e sistema observado
somente depois de executar o percurso real. O aceite vincula o **SHA exato** do
DMG e sua arquitetura. Uma primeira rodada pode oferecer apenas arm64, por
exemplo, omitindo Intel do portal. Cada arquitetura oferecida precisa dos dois
percursos visíveis no app: Mac local e servidor. Reduzir `offered_modes` no JSON
não dispensa uma escolha que continua visível na interface.

O aceite local inclui instalação vazia, importação/Hoje com fontes, sair sem
Terminal, reabrir/login/suspensão, snapshot/restauração e atualizações assinadas
do app e backend preservando contexto. O remoto inclui SSH verificado,
instalação vazia, fontes/Hoje, reinício do servidor, reconexão, snapshot/restore
e atualização do backend preservando contexto. Automação WKWebView/launchd
auxilia a revisão; não registra clique humano, boot ou suspensão como aprovados.

Executar `plan` com os recibos e o aceite. Revisar `blocked_gates`, origem,
versão, hashes e chaves. `stage --help` lista os conjuntos completos de DMG,
atestação e wheelhouse por arquitetura. `stage` exige o hash exato do plano,
assinaturas válidas e fonte/wheels iguais aos incorporados nos apps. Uma versão
anterior não é sobrescrita. `refresh` renova a validade do feed conservando os
mesmos artefatos e aceites; não simula uma atualização de versão.

## Upload e publicação final

Com estado de publicação aprovado e IDs públicos dos dois stores já conferidos:

```bash
python3 scripts/deploy_demo_distribution.py plan \
  --domain nome-do-projeto.vercel.app --project-name nome-do-projeto \
  --private-store-id ID_PRIVADO --public-store-id ID_PUBLICO \
  --state "$HOME/mia-release-work/publisher" \
  --output "$HOME/mia-release-work/release-plan.json"
```

Revisar o plano, incluindo origem, release e recursos gratuitos. `upload`
exige `--approve-sha256` desse plano e credenciais já vinculadas ao ambiente do
operador. Faz streaming, proíbe sobrescrita e lê o objeto novamente para conferir
tamanho e SHA256. Repetir pode adotar somente bytes idênticos já existentes.
Falha não troca o release ativo. Guardar o inventário de upload privado.

```bash
python3 scripts/deploy_demo_distribution.py kit \
  --plan "$HOME/mia-release-work/release-plan.json" \
  --state "$HOME/mia-release-work/publisher" \
  --uploads "$HOME/mia-release-work/uploads.json" \
  --output "$HOME/mia-release-work/release-kit"
```

O kit final mantém DMGs no Blob privado. A Function devolve apenas uma
autorização de leitura de um objeto por até 60 segundos, evitando passar um DMG
grande pelo limite de resposta da Function. Appcasts exigem Bearer beta e não
são arquivos públicos. Pacotes-fonte Apache são públicos, autenticados por
feed Ed25519. Rotas imutáveis de releases anteriores permanecem disponíveis
para retomadas e feeds ainda válidos.

Publicar esse kit na mesma origem estável usando a Vercel conectada. Executar:

```bash
python3 scripts/deploy_demo_distribution.py verify \
  --kit "$HOME/mia-release-work/release-kit"
```

Esse comando verifica HTTPS/identidade do release e rejeição do appcast sem
ativação. Ele declara `actual_beta_activation_and_download_verified=false`:
**não substitui o ensaio completo**. Antes de convidar participantes, usar um
convite de teste para conferir no HTTPS final: resgate, download por leitura
privada, repetição após resposta perdida, ativação pelo app/Keychain,
atualização privada, expiração/revogação e biblioteca operando sem o portal.
Registrar os resultados reais junto do aceite, sem copiar tokens para logs.

## Convites e revogação

Após os aceites, emitir um link individual em arquivo privado:

```bash
python3 scripts/deploy_demo_distribution.py issue-invite \
  --kit "$HOME/mia-release-work/release-kit" --days 7 \
  --output "$HOME/mia-release-work/convite-001.json"
```

O operador escolhe destinatários e envia o link. O comando **não envia
mensagens** e imprime somente ID/caminho. Não anexar esse JSON a issues/PRs.
`list-invites` exibe IDs e datas, sem tokens; `revoke-invite --id ID` revoga o
convite e suas autorizações futuras de distribuição.

O link leva o token no fragmento, removido no navegador antes de qualquer POST.
O resgate único fica vinculado à arquitetura e ao nonce privado de repetição,
com sessão de download de até 24 horas. O app abre
`mia-demo://activate?ticket=…`, envia o ticket à origem embarcada e guarda a
autorização de atualizações de até 90 dias no Keychain. Essa autorização não é
login da biblioteca pessoal nem licença de uso do código aberto.

Revogar impede novos links e acessos ao appcast; um link já emitido dura no
máximo os 60 segundos restantes e uma transferência já aceita pode terminar.
Arquivos já baixados não são apagados. A biblioteca instalada, exportação e
recuperação continuam disponíveis offline quando convite, portal ou token
expiram. Não implementar desligamento remoto do contexto pessoal.

## Referências e verificação

O protocolo Blob foi conferido contra `@vercel/blob` **2.8.2**, tarball npm de
SHA256 `329e8dad6317e89eff2d76a42c1e765b91b4a5039cac279adb17d2a3fec93d64`
e integridade SHA512 publicada. A Mia implementa o protocolo em Python; não
distribui nem depende do SDK JavaScript. Fontes de referência:
[pacote npm](https://www.npmjs.com/package/@vercel/blob/v/2.8.2),
[repositório oficial](https://github.com/vercel/storage),
[Hobby](https://vercel.com/docs/plans/hobby),
[Blob e limites](https://vercel.com/docs/vercel-blob/usage-and-pricing),
[limites de Functions](https://vercel.com/docs/functions/limitations).
As quotas atuais e a disponibilidade de cada recurso precisam ser confirmadas
na conta antes da publicação; links de documentação não são essa confirmação.

Os testes usam dados sintéticos, Redis real isolado por Unix socket para os
scripts Lua atômicos, reinícios e corridas de resgate/ativação. Provedores HTTP
simulados validam contratos e falhas. Esses testes não comprovam um deploy na
conta Vercel nem notarização Apple. O kit sem release também é importado e
executado em subprocesso para confirmar sua resposta 503.


## Registro de provisionamento — 15/10/2026

Origem estável publicada: **https://mia-beta-distribution.vercel.app**.
Projeto separado `mia-beta-distribution`, equipe `giulioggp`; nenhum projeto
existente, Mac, servidor ou Vault foi modificado. Kit gerado pelos comandos
`plan`/`kit` a partir da revisão limpa `1e30564d365a8e14e4138fd6e7a8f2506866f4f8`.
Não foi implantado o checkout inteiro. Versão do produto permanece 0.2.0a14.

| Recurso | Evidência |
| --- | --- |
| Conta | API autenticada informa Hobby ativo, sem trial; nenhum upgrade contratado |
| Projeto | `prj_AJJKDMIZ5lxPsNXdohHOl9KfHOC5`, framework automático desativado, kit Python separado |
| Deploy inicial | `dpl_3NMiTSWbPjqGFzPCBN5qT8GTCyN4`, produção, READY |
| Deploy após restringir variáveis | `dpl_BXZhXSz3frhzvhBgLvj6DUZjdqsh`, produção, READY; mesmos fontes do kit |
| Blob privado | `store_CIIPyIi6ZKAeEIGQ`, `mia-beta-dmgs`, iad1, disponível, 0 bytes/objetos, quota não excedida |
| Blob público | `store_g8GPAd8STBlHm5JC`, `mia-beta-backend`, iad1, disponível, 0 bytes/objetos, quota não excedida; sem token de escrita na Function |
| Variáveis | `BLOB_READ_WRITE_TOKEN` vinculado pelo provedor, convertido para sensitive e somente production; `BLOB_STORE_ID` definido somente em production. Valores secretos não foram exibidos ou versionados |
| Upstash | Nenhuma configuração instalada retornada pelo plugin; criação/instalação da integração não está disponível nas ferramentas expostas |

A origem consta nos aliases do deploy e nos domínios do projeto. Uma tentativa
redundante de adicioná-la retornou 409; a inspeção posterior confirmou a associação
e o HTTPS respondeu com o conteúdo esperado. Não se tentou transferir domínios.

Verificação sem autenticação/bypass, por HTTPS: GET `/health`, `/`, `/invite`,
`/distribution-release.json`, `/deployment-plan.json` e
`/updates/arm64/appcast.xml` responderam 503 com `ready_for_beta=false` e
`Cache-Control: no-store`. Metadados privados e appcast não foram expostos.
POST `/redeem` respondeu 405: o kit preparatório não instala a rota de resgate.
Isso comprova preparação indisponível, **não** o ciclo final de convites.
A consulta de logs de erro/fatal do deploy inicial nos 30 minutos da verificação
não retornou registros; não constitui monitoramento contínuo.

Testes desta sessão: 49 passaram nos módulos `test_vercel_release.py` e
`test_vercel_distribution.py`; 10 cenários Redis foram ignorados por falta do
executável local. Não se reclassificaram esses cenários como aprovados nesta
sessão. Usado Python 3.12 com dependências já disponíveis no ambiente de trabalho;
não é um novo ensaio integral de instalação do lock. A evidência anterior de
Redis real/722 testes e CI nativo permanece vinculada às revisões já registradas.
Nenhuma mudança no código do aplicativo foi necessária nesta publicação.

### Gratuidade e capacidade

Documentação oficial consultada em 15/10: Hobby destina-se a uso pessoal não
comercial. A conta ativa não decide por si só a elegibilidade de uma futura
operação comercial. Não foi ativada monetização, trial Pro ou cobrança adicional.
Antes de mudar o uso, revisar esse requisito com o titular.

[Hobby](https://vercel.com/docs/plans/hobby) inclui, entre outros limites,
100 GB de transferência rápida e 1 milhão de invocações; [Blob](https://vercel.com/docs/vercel-blob/usage-and-pricing)
inclui 1 GB-mês de armazenamento, 10 GB de transferência, 10.000 operações simples
e 2.000 avançadas. Estourar a quota gratuita pode suspender o recurso; não aumenta
a capacidade automaticamente. Esses são limites publicados, não uma medição do
saldo global da equipe. Os stores novos informam zero uso e quota não excedida.

**Ainda não há comprovação de capacidade para os DMGs/wheels finais e retenção.**
Somar bytes das arquiteturas oferecidas, versões conservadas e downloads previstos
antes do upload; não reduzir gates de assinatura/aceite para caber na quota.
Não há promessa de custo fixo ou disponibilidade contínua a partir deste preparo.

### Bloqueios concretos para liberar convidados

1. Upstash Free provisionado pelo proprietário e vinculado via conectores em 15/10;
   conferir dimensionamento dos convites e ensaio completo antes da liberação.
2. Apple Developer, Developer ID Application, perfil notarytool e Mac de assinatura;
   gerar canais com esta origem e chaves públicas reais antes de assinar.
3. Build/atestação Apple e aceites nos aparelhos finais por arquitetura/modalidade,
   incluindo login/suspensão, atualização assinada, restauração e servidor oferecido.
4. Confirmar capacidade, enviar artefatos verificados e publicar o kit final.
5. Ensaiar no HTTPS real convite → download → ativação/Keychain → atualização →
   revogação e independência da biblioteca. Só então emitir arquivos privados de
   convite para destinatários escolhidos pelo proprietário. Nenhum convite foi
   emitido ou enviado; o portal não recebeu conteúdo pessoal nem chaves de IA.


### Redis Free vinculado — 15/10/2026

O proprietário criou `mia-beta-invites` (ID
`b495258d-b2ac-4b12-91ab-bd8a33159b26`). O conector Upstash confirmou
plano `free`, estado `active`, região primária `us-east-1`, TLS ativo,
`auto_upgrade=false` e `eviction=false`. Nenhum upgrade foi contratado.

Credenciais obtidas pelo conector e transmitidas diretamente à Vercel, sem
valores no chat, arquivos ou Git. `UPSTASH_REDIS_REST_URL` é configuração e
`UPSTASH_REDIS_REST_TOKEN` é sensível; ambas restritas a `production`.
A integração é direta por variáveis REST; não foi instalada uma integração
Marketplace, nem é necessária para esse caminho.

Verificação real pelo conector: `PING` retornou `PONG`; `EVAL` executou
SET com TTL de 120 segundos e GET na chave sintética isolada
`{mia-provisioning-check}:20261015`, retornando o valor esperado. A chave
expira automaticamente. Isso comprova acesso REST e operação Lua; não é
ensaio de reinício/restauração nem percurso de convite com o app final.

Redeploy de produção `dpl_5iY3rLnKFPnVxMW8SNzV88AbCMXE` confirmado
`READY`, alias https://mia-beta-distribution.vercel.app, usando o kit
preparatório existente. O kit sem release aprovado não instancia o registro
de convites: a validação Redis foi feita pelo conector, não por uma emissão
de convite via Function. Nenhum convite real foi emitido. Não houve alteração
de código; testes Python/Swift anteriores mantêm seus escopos registrados.

Após o redeploy, GET HTTPS público em `/health` e `/invite` confirmou 503,
`ready_for_beta=false` e `Cache-Control: no-store`.
