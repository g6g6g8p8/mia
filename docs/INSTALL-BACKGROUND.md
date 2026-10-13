# Usar Mia sem manter Terminal aberto

A 0.2.0a12 oferece serviço de usuário e migração de uma instalação Python manual parada. A instalação inicial abaixo ainda é administrativa. Depois dela, o uso diário acontece no navegador; fechar navegador ou Terminal não significa parar Mia. O launcher gráfico Mac e seu empacotador estão no código, mas assinatura, notarização e aceite em Mac limpo continuam pendentes. Não há aplicativo nativo para iPhone nem sincronização offline entre bancos.

## Escolher onde fica a instalação

| Escolha | Uso diário | Disponibilidade |
| --- | --- | --- |
| Mac local | Abrir o endereço local no navegador; LaunchAgent inicia no login | O Mac precisa estar ligado e acordado. Acesso do iPhone exige rede/acesso preparados separadamente |
| Servidor Linux | Mac e iPhone abrem o mesmo endereço HTTPS | Serviço e rede precisam estar disponíveis; usuário systemd precisa de linger para funcionar após boot sem login |

Cada instalação tem seu próprio banco. Acessar o mesmo servidor em dois dispositivos usa esse banco compartilhado; instalar duas Mias não as sincroniza. GitHub distribui código e não recebe automaticamente notas, chaves ou conversas.

## Instalação gerenciada nova

Use Python 3.12 ou 3.13 disponível no sistema e uma revisão confiável do código. Escolha um diretório privado **novo**, fora do checkout. O gerenciador preserva um runtime separado por versão.

```bash
cd /caminho/do/checkout/mia
MIA_INSTALL_ROOT="$HOME/.local/share/mia"
python3 scripts/native.py --root "$MIA_INSTALL_ROOT" install --source "$PWD"
```

Se o diretório já contém uma instalação gerenciada, siga atualização/recuperação em [OPERATIONS.md](OPERATIONS.md); não reinstale por cima. O bootstrap `manager.py` da a11 não recebe os novos comandos por uma atualização comum do aplicativo. A ativação de serviço recusa esse bootstrap: prepare uma instalação gerenciada nova e migre os dados com a origem parada. `--wheelhouse /caminho --offline` permite instalar com wheels revisados compatíveis sem buscar pacotes.

## Trazer uma instalação manual existente

Pare o uvicorn anterior com `Ctrl+C` no Terminal onde está rodando. Confira que não há processo usando os dados; uma porta livre sozinha não prova isso. Preserve uma cópia externa antes da migração. O comando exige declaração explícita de que a origem está parada; recusa destinos já preenchidos e não apaga a origem.

```bash
python3 scripts/native.py --root "$MIA_INSTALL_ROOT" migrate-data \
  --data-source /caminho/da/instalacao-anterior/data --source-stopped
```

`--source-env-file /caminho/do/arquivo.env` é opcional e somente aceita configurações Mia reconhecidas; não execute nem passe um arquivo de outro produto. Configuração salva pela interface dentro dos dados também é preservada. Snapshot operacional pode conter credenciais e precisa permanecer privado. Migração não busca automaticamente pastas ou chaves de outra máquina.

## Ativar na conta atual

Gere um plano novo com o tipo do sistema: `launchd` no Mac ou `systemd` no Linux. O plano inclui arquivo, comandos exatos, alcance e hash. Leia o JSON completo antes de aplicar.

```bash
python3 scripts/install_service.py --root "$MIA_INSTALL_ROOT" service-plan \
  --kind launchd --output /caminho/privado/mia-service-plan.json
```

No Linux, substitua `launchd` por `systemd`. Depois da revisão:

```bash
python3 scripts/install_service.py --root "$MIA_INSTALL_ROOT" service-apply \
  --plan /caminho/privado/mia-service-plan.json \
  --approve-sha256 HASH_EXATO_MOSTRADO_NO_PLANO
python3 "$MIA_INSTALL_ROOT/manager.py" --root "$MIA_INSTALL_ROOT" status
```

A aplicação recusa plano alterado, hash diferente, sistema incompatível, caminho com symlink ou substituição de arquivo de outro serviço. Não usa sudo, não abre portas e não prepara domínio. `systemd --user` depende do gerenciador de sessão da máquina; em servidor que deve continuar sem login, o operador precisa revisar/habilitar linger para a conta escolhida. Isso é separado do plano.

O supervisor limita reinícios após falhas e aguarda atualização/recuperação. Desligamento ou fim da sessão encerra o processo; o próximo login/boot autorizado pode iniciar novamente. **Parar explicitamente** grava uma pausa persistente, que também afeta outros dispositivos:

```bash
python3 "$MIA_INSTALL_ROOT/manager.py" --root "$MIA_INSTALL_ROOT" stop
python3 "$MIA_INSTALL_ROOT/manager.py" --root "$MIA_INSTALL_ROOT" start
```

`start` libera a pausa. Não rode uvicorn manual, supervisor e serviço independentes sobre os mesmos dados. [ACCESS.md](ACCESS.md) explica como preparar HTTPS e conferir acesso real do iPhone; selecionar “servidor” no onboarding apenas registra onde a instalação existente está rodando.

## Launcher Mac e aceites restantes

`scripts/package_macos.py` monta `.app` com runtime standalone e wheels offline de origem e hashes explícitos, separados por arquitetura. `mia.launcher` oferece instalação local ou conexão ao endereço HTTPS existente e preserva o runtime em caminho estável fora do bundle. Fechar a janela deixa o serviço em segundo plano.

Testes Linux verificam contratos, integridade dos artefatos e processos de serviço; não executam Mach-O, launchd real ou assinatura. Não distribuir como instalador Mac pronto antes de conferir instalação sem Python/Git no Mac limpo, login, suspensão, retomada, atualização/restauração e assinatura/notarização. Nenhuma instrução para ignorar Gatekeeper faz parte deste fluxo.
