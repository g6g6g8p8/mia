# Publicação privada do beta Mac

15/10/2026. Este procedimento é do responsável pela distribuição. O convidado
baixa o app, abre seu convite na Mia e escolhe instalar no próprio Mac ou em seu
servidor. Ele não executa estes comandos.

## Estado e recursos

O código prepara uma publicação imutável, um portal Vercel, convites duráveis e
atualizações privadas. **Não há publicação Vercel nem convite real comprovados
nesta execução.** A conta Apple Developer, o build assinado/notarizado e os
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
avisos originais. Não contém segredos nem DMGs. Sem release aprovado, todas as
requisições ao app retornam **503**, com `ready_for_beta=false`. Isso permite
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
