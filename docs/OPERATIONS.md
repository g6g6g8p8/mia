# Operação nativa e atualização consciente — 0.2.0a11

Alternativa para **instalações novas**, com Python 3.12+ no Linux ou macOS. O modo manual e o Docker continuam suportados. O gerenciador não controla containers, volumes, firewall ou DNS; não recebe comandos do navegador nem do modelo. Use somente uma distribuição/fonte local que você revisou e cuja origem confia.

## Instalar e iniciar

Na pasta da distribuição da Mia, escolha um diretório novo **fora do checkout**:

```bash
MIA_INSTALL_ROOT="$HOME/.local/share/mia"
python3 scripts/native.py --root "$MIA_INSTALL_ROOT" install --source "$PWD"
python3 "$MIA_INSTALL_ROOT/manager.py" --root "$MIA_INSTALL_ROOT" start
python3 "$MIA_INSTALL_ROOT/manager.py" --root "$MIA_INSTALL_ROOT" status
```

O instalador cria versões separadas e seus ambientes virtuais, instala o lockfile e verifica a versão do pacote fora do diretório-fonte. Não copia `.env`, dados, backups, testes nem histórico Git do checkout. O diretório privado usa 0700 e arquivos de estado/configuração 0600. Falha de preparação não cria uma versão ativa; preserve o diretório parcial e escolha um destino novo para outra tentativa. Nenhuma instalação existente é sobrescrita.

A aplicação nasce vazia, IA desativada, em `127.0.0.1:8123`. `start` confirma saúde e versão por HTTP, usando socket próprio e um único worker. A porta de outra aplicação não pode confirmar essa inicialização. Uma tentativa de iniciar outro serviço durante atualização é recusada. `stop` sinaliza apenas um processo com identidade e lock verificáveis.

`machine.env` é a configuração desta instalação. Aceita apenas `MIA_*`, exceto `MIA_DATA_DIR`, `MIA_OPERATIONS_ROOT` e `MIA_BIND`, controlados pelo gerenciador. Variáveis MIA herdadas do terminal não substituem esse arquivo. Para preparar HTTPS, adicione `MIA_COOKIE_SECURE=true` ao arquivo existente, preservando outras opções; pare e reinicie conforme [ACCESS.md](ACCESS.md). Não coloque valores secretos em scripts ou relatos. Arquivos salvos pela própria interface continuam no diretório de dados da instalação.

## Atualizar

Escolha e confira a versão em outra pasta local; não atualize durante geração. Mantenha uma cópia de backup em outro disco.

```bash
python3 "$MIA_INSTALL_ROOT/manager.py" --root "$MIA_INSTALL_ROOT" status
python3 scripts/native.py --root "$MIA_INSTALL_ROOT" update --source /caminho/da/versao-revisada
```

A versão candidata é instalada antes de parar o serviço. Depois da parada comprovada, cria um snapshot íntegro do banco **e dos arquivos privados/configuração**. Registra a operação em disco antes de trocar a versão ativa. A nova versão só é confirmada após saúde e versão corretas por HTTP. Enquanto houver operação pendente, alterações pela API recebem HTTP 503, inclusive login/setup; `/health` e `/api/status` continuam disponíveis para o diagnóstico de startup.

Uma falha de startup restaura o estado anterior em diretório novo e tenta iniciar a versão anterior. O banco da tentativa fica preservado. A falha permanece explícita no comando; uma recuperação automática não transforma o resultado em sucesso de atualização. Se a recuperação também falhar, o registro pendente fica preservado e o comando informa que é necessário `recover`.

## Recuperar e retornar

```bash
python3 "$MIA_INSTALL_ROOT/manager.py" --root "$MIA_INSTALL_ROOT" recover
python3 "$MIA_INSTALL_ROOT/manager.py" --root "$MIA_INSTALL_ROOT" status
```

`recover` usa o snapshot verificado e a versão anterior; uma repetição após interrupção da recuperação retoma **o mesmo diretório restaurado**. Não aceita snapshot adulterado ou banco restaurado ausente e não recria dados vazios para encobrir essa falha. Sessões anteriores são invalidadas. Gerações interrompidas não são reenviadas.

Para voltar após uma atualização já confirmada, revise a diferença de dados antes de executar:

```bash
python3 "$MIA_INSTALL_ROOT/manager.py" --root "$MIA_INSTALL_ROOT" rollback --acknowledge-post-update-loss
```

O retorno ativa o estado **anterior à atualização**. Alterações feitas depois ficam em banco/diretório e snapshot separados, mas não aparecem no banco ativo restaurado. O comando exige ciência explícita dessa diferença, não mescla bancos e não executa código antigo sobre banco migrado. Preserve os diretórios até revisar os dados; há apenas retorno da última atualização confirmada, não seleção de qualquer versão histórica.

## Boot e instalação offline

O comando `service-template --kind systemd` ou `--kind launchd` imprime um template para revisão. Nada é instalado ou habilitado automaticamente. Os templates usam o supervisor em primeiro plano e não reiniciam durante atualizações. No Linux, use uma unidade de usuário; no Mac, um LaunchAgent do próprio usuário. Ativação com `systemctl --user`/`launchctl`, boot e suspensão dependem do sistema de destino e continuam exigindo ensaio nessa máquina. Não use simultaneamente supervisor direto, unidade e servidor manual apontando para os mesmos dados.

```bash
python3 "$MIA_INSTALL_ROOT/manager.py" --root "$MIA_INSTALL_ROOT" service-template --kind systemd
python3 "$MIA_INSTALL_ROOT/manager.py" --root "$MIA_INSTALL_ROOT" service-template --kind launchd
```

`install` e `update` aceitam `--wheelhouse /diretorio --offline`. Prepare nesse diretório os wheels de `requirements.lock` e `pip==25.0.1`, `setuptools==75.8.0`, `wheel==0.45.1`, compatíveis com o Python/arquitetura de destino, obtidos de origem confiável com verificação preservada. O modo offline usa `--no-index`; artefatos ausentes falham em vez de buscar outra origem.

## Diagnóstico e limites

Sistema → Operação e atualização mostra versão, modo e recuperação pendente. É uma consulta autenticada, sem caminhos/credenciais, e não executa comandos. `service.log` fica no diretório privado; revise antes de compartilhar. Snapshots operacionais **podem conter chaves**, não são criptografados e permanecem no mesmo disco. Não substituem cópia externa nem ensaio de restauração.

O script `scripts/native_lifecycle.py` usa fontes e dados sintéticos em diretórios temporários para instalar versões, testar HTTP, atualização, falha, recuperação e retorno. Os testes de processo simulam interrupções e SIGKILL; não equivalem a queda elétrica física. Mac/boot, infraestrutura HTTPS pública e operação por participantes continuam aceites externos, sem alegação de validação por esses ensaios Linux.

O bootstrap privado `manager.py` é fixado na instalação e atualiza a aplicação, não a si próprio. Não considere futuras correções desse bootstrap aplicadas por uma atualização comum. A a12 registra protocolo/hash e recusa serviço/migração com bootstrap a11 incompatível ou alterado. Nesse caso, prepare uma instalação gerenciada nova e migre dados com a origem parada; não substitua bootstrap durante recuperação incompleta. O procedimento de serviço e migração manual está em [INSTALL-BACKGROUND.md](INSTALL-BACKGROUND.md).

Snapshots operacionais a12 excluem `migration-staging` por padrão: arquivos brutos e textos ainda não aprovados não viram backup permanente. Metadados/progresso do job e fontes já aprovadas continuam no banco. Depois de restaurar, jobs incompletos sem staging exigem reenviar a origem; não são transformados em migração concluída.
