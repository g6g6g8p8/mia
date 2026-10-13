# Recomeçar a Mia com uma instalação vazia

13/10/2026 · procedimento administrativo da alpha 0.2.0a12. O uso diário fica no navegador, com serviço em segundo plano. O instalador Mac assinado e a validação em Mac limpo ainda precisam ser concluídos antes de chamar esse caminho de instalação para público geral.

O objetivo é tirar instalações anteriores de uso, preservar uma recuperação privada e criar um banco novo. Reinício da experiência não requer apagar o vault, exports, backups ou credenciais de outros produtos. Cada beta-tester instala uma Mia própria; Mac e iPhone acessando o mesmo servidor usam uma instalação compartilhada, enquanto duas instalações não sincronizam seus bancos.

## 1. Inventariar antes de mudar as máquinas

Execute [installation_inventory.py](../scripts/installation_inventory.py) no Mac e no servidor com Python do sistema. O script usa apenas biblioteca padrão, não carrega a Mia existente e não altera arquivos nem serviços. Confira o arquivo antes de executar. Não use `curl | sh`, não cole chaves no chat e não publique o relatório junto com dados pessoais.

Com o script já disponível localmente:

```bash
python3 /caminho/revisado/installation_inventory.py
```

Para usar a mesma cópia no servidor:

```bash
MIA_SSH_TARGET='USUARIO@SERVIDOR'
scp /caminho/revisado/installation_inventory.py "${MIA_SSH_TARGET}:/tmp/mia-installation-inventory.py"
ssh "$MIA_SSH_TARGET" 'python3 /tmp/mia-installation-inventory.py'
```

Preencha o destino SSH na própria máquina; ele não é configuração para publicar no repositório.

O inventário procura somente candidatos conhecidos e os caminhos exatos passados por `--candidate`. Mostra identificação do checkout/gerenciador, presença de banco/configuração, serviços com nomes Mia, containers candidatos e nomes/PIDs de listeners. Não lê notas, arquivos `.env`/`machine.env`, consulta variáveis de ambiente ou mostra argumentos completos de processos. Definições de serviço são lidas para reconhecer a Mia e calcular hash; seus argumentos/ambiente não aparecem no relatório. Caminhos com links são recusados. Um candidato ou PID não comprova que pode ser parado ou removido; porta livre não prova que nenhum processo está usando os dados. Diretórios personalizados e serviços com outro nome exigem uma verificação adicional.

Em instalações piloto existentes, estes são candidatos comuns, ainda a confirmar:

| Máquina | Candidato a confirmar agora | Preservar fora da limpeza |
| --- | --- | --- |
| Mac | `~/mia-onboarding`, possível instalação manual | Todo `~/mia-backups`, vaults e exports originais |
| Servidor Linux | `~/mia-pilot`, tipo ainda a identificar | Outros serviços, vaults, backups e certificados existentes |

Também podem existir instalações gerenciadas em `~/.local/share/mia` ou `~/Library/Application Support/Mia/installation`. Não execute limpeza de Docker, disco, Homebrew ou Python global. Não pare outros produtos, não revogue uma chave de IA usada por outro produto e não altere o proxy compartilhado por dedução.

Registre para cada Mia confirmada: raiz exata, diretório de dados efetivo, versão/revisão, mecanismo de serviço, executável Python, exposição de rede e configuração privada a preservar. Se o relatório aponta recuperação pendente, resolva ou preserve esse estado antes de seguir [OPERATIONS.md](OPERATIONS.md).

O inventário reconhece o gerenciador a11 sem campo `manager_protocol` como candidato legado, com configuração, ponteiros ativos e marcadores de código válidos. Isso não autoriza alteração automática. Ele informa caminhos de runtime e bootstrap sem executá-los: para `mia.backup`, use o **runtime da aplicação** — `releases/.../venv/bin/python` na instalação gerenciada ou `.venv/bin/python` na manual. O Python de bootstrap registrado em `installation.json` pode não ter o módulo Mia instalado. Links do executável de venv são comuns, mas precisam de revisão local antes do uso.

## 2. Parar somente a Mia identificada

Antes de parar, conclua ou cancele importações ainda em envio/revisão pela interface. Staging temporário não aprovado é excluído dos snapshots operacionais por padrão. Caso não consiga concluir/cancelar, preserve as origens para reenviar, registre os jobs incompletos e exclua `migration-staging` da cópia permanente; não arquive uploads temporários indefinidamente. Jobs aprovados e fontes publicadas permanecem no banco. O fluxo antigo de importação guardava revisão no SQLite: seus backups podem conter aquele conteúdo, conforme [ONBOARDING.md](ONBOARDING.md).

Use o mecanismo que corresponde à instalação, depois de confirmar que ele aponta para a Mia e para a raiz escolhida:

- **Manual:** `Ctrl+C` no Terminal que iniciou aquele uvicorn. Se a janela desapareceu, identifique o processo pelo executável, diretório e módulo Mia antes de enviar sinal; não use `pkill python` nem mate todo processo na porta 8123.
- **Gerenciada:** execute `stop` pelo `manager.py` daquela raiz. A pausa é persistente e afeta os dispositivos conectados.
- **systemd/launchd:** depois da parada, desative apenas a unidade/LaunchAgent Mia identificado, para que o login/boot não reabra a instalação antiga. Guarde sua definição no arquivo privado da limpeza.
- **Docker:** pare apenas o container/serviço Mia confirmado, preservando volume e definição. Não execute `docker compose down` num projeto compartilhado e não use `docker system prune`, `docker volume prune` ou remoção automática de volumes.

Exemplo para uma **raiz gerenciada já confirmada**:

```bash
MIA_OLD_ROOT='/caminho/exato/confirmado'
MIA_OLD_PYTHON='/caminho/exato/do/runtime-python-da-aplicacao'
"$MIA_OLD_PYTHON" "$MIA_OLD_ROOT/manager.py" --root "$MIA_OLD_ROOT" stop
```

Para serviço de usuário Linux confirmado, o desligamento é `systemctl --user disable --now NOME_EXATO_MIA.service`. No Mac, use `launchctl bootout gui/$(id -u) /caminho/exato/do/LaunchAgent-Mia.plist`. Arquive o arquivo de registro para que ele não volte no próximo login. Não copie nomes de serviço de outra instalação e não desative todos os serviços do usuário.

Confira a ausência do processo escritor e do supervisor antigo, do registro ativo e do listener esperado. O restante da cópia pressupõe a origem parada. Não execute simultaneamente duas Mias sobre os mesmos dados.

## 3. Preservar, verificar e ensaiar recuperação

Crie destino novo fora de qualquer checkout Git, com permissões privadas:

```bash
umask 077
mkdir -p "$HOME/mia-backups"
chmod 700 "$HOME/mia-backups"
MIA_SAFETY_COPY=$(mktemp -d "$HOME/mia-backups/antes-da-limpeza.XXXXXX")
```

Com a origem parada, copie o diretório de dados para essa pasta, incluindo WAL/SHM quando presentes e excluindo `migration-staging` conforme o passo anterior; preserve separadamente suas configurações privadas Mia e definições de serviço. Use os caminhos efetivos obtidos no inventário. Copiar só `mia.db` pode perder o WAL; copiar arquivos de um banco em uso pode gerar cópia inconsistente. Para instalações Docker, consulte o mapeamento de volume confirmado antes de copiar. Não copie `.env` de outro produto para a Mia.

Valide o banco copiado, crie um snapshot SQLite consistente a partir **da cópia** e faça restauração em outra pasta nova, usando o runtime correspondente à versão anterior. Os comandos são os de [BACKUP.md](BACKUP.md). Exemplo após definir caminhos conferidos:

```bash
MIA_COPIED_DATA='/caminho/privado/da/copia/data'
MIA_SNAPSHOT='/caminho/privado/novo/mia-snapshot.db'
MIA_RESTORE_TEST='/caminho/privado/novo/ensaio-restauracao'
cd "$HOME"
env MIA_DATA_DIR="$MIA_COPIED_DATA" "$MIA_OLD_PYTHON" -m mia.backup backup "$MIA_SNAPSHOT"
"$MIA_OLD_PYTHON" -m mia.backup verify "$MIA_SNAPSHOT"
"$MIA_OLD_PYTHON" -m mia.backup restore "$MIA_SNAPSHOT" "$MIA_RESTORE_TEST"
```

Abra temporariamente essa restauração em loopback e porta livre distinta, confira `/health`, login e uma fonte/tarefa conhecida e pare o ensaio. Não habilite IA nesse ensaio. O runtime precisa ser o da versão anterior, executado fora do checkout novo para evitar importar código de outra revisão. Se o banco ainda não tinha proprietário, confirme o mesmo estado `configured:false`. Configurações privadas são preservadas separadamente, pois não entram no snapshot SQLite. Uma cópia que só passou `verify` ainda precisa desse ensaio de uso.

Snapshots SQLite não incluem chaves/configuração de IA e acesso. A cópia de configuração e o arquivo completo de instalação podem conter segredos: mantenha-os privados e em disco protegido. Guarde também uma cópia fora da máquina; arquivamento no mesmo disco permite desfazer a limpeza, mas não protege de perda do disco. Dados da Mia antiga não devem ser importados automaticamente na instalação nova.

## 4. Arquivar a instalação anterior

Depois de testar a recuperação, mova **somente a raiz Mia confirmada** para um diretório privado novo de arquivo, fora de Git. Mover em vez de apagar permite desfazer o recomeço. Confira antes que o staging de jobs concluídos/cancelados foi removido; staging de jobs incompletos deve ser excluído deliberadamente, com as origens preservadas para reenviar. Preserve cópia das unidades/proxy específicos de Mia e mantenha outros produtos intactos. O backup de segurança do passo anterior é independente desse movimento.

Use a raiz verificada no inventário; nunca passe `$HOME`, `/` ou uma pasta contendo outros produtos como raiz da Mia. Não faça `rm -rf` de candidatos. Para Docker, mantenha os volumes antigos desconectados e identificados; a instalação nova precisa de um volume/diretório novo.

Ao terminar, confirme que a Mia antiga não volta ao reabrir Terminal, fechar SSH ou reiniciar a máquina. Confira separadamente que os demais serviços preservados continuam funcionando. Se existir uma publicação HTTPS antiga exclusiva da Mia, retire apenas aquela rota após guardar sua definição; não redefina configuração compartilhada do proxy/túnel.

## 5. Criar a instalação nova

Escolha **Mac local** ou **servidor Linux**. Ambos precisam passar seus próprios aceites antes dos convites. Use Python **3.12 ou 3.13** conferido com `--version`. Não presuma que o nome `python3` aponta para essa versão. Se não existe um Python suportado, obtenha-o pelo canal oficial e teste antes de continuar; a Mia não deve substituir o Python de outros produtos.

Crie checkout novo somente de código e fixe uma revisão completa revisada; não instale da branch móvel sem registrar qual commit foi usado:

```bash
MIA_REVISION='REVISAO_COMPLETA_REVISADA'
MIA_CODE_ROOT="$HOME/mia-code"
git clone https://github.com/g6g6g8p8/mia.git "$MIA_CODE_ROOT"
git -C "$MIA_CODE_ROOT" checkout --detach "$MIA_REVISION"
git -C "$MIA_CODE_ROOT" rev-parse HEAD
```

Substitua o marcador pelo SHA completo revisado da entrega a12, obtido na página da release/PR aprovada. Confira o SHA mostrado pelo checkout antes de executar scripts. Os diretórios precisam ser novos; se já existem, escolha outros nomes. Dados, arquivos `.env`, snapshots e planos ficam fora desse checkout.

Com `MIA_BOOTSTRAP_PYTHON` definido para o executável suportado:

```bash
MIA_INSTALL_ROOT="$HOME/.local/share/mia"
"$MIA_BOOTSTRAP_PYTHON" "$MIA_CODE_ROOT/scripts/native.py" --root "$MIA_INSTALL_ROOT" install --source "$MIA_CODE_ROOT"
```

O gerenciador cria ambiente isolado por versão e dados vazios. Não reutilize `.venv` da instalação antiga nem rode `pip` no Python global. Caso o Python não consiga criar um venv com pip, corrija o suporte a venv/ensurepip naquele Python antes da instalação. Se a raiz já existe, pare e escolha uma raiz nova; não reinstale por cima.

Gere o plano do serviço em pasta privada nova. No Mac escolha `launchd`; no Linux, `systemd`:

```bash
MIA_SERVICE_PLAN="$HOME/mia-backups/novo-servico-mia.json"
"$MIA_BOOTSTRAP_PYTHON" "$MIA_CODE_ROOT/scripts/install_service.py" --root "$MIA_INSTALL_ROOT" service-plan --kind systemd --output "$MIA_SERVICE_PLAN"
```

Leia o plano completo: destino, comandos, conta atual, endereço, política de reinício e hash. Depois aplique exatamente o hash revisado:

```bash
"$MIA_BOOTSTRAP_PYTHON" "$MIA_CODE_ROOT/scripts/install_service.py" --root "$MIA_INSTALL_ROOT" service-apply --plan "$MIA_SERVICE_PLAN" --approve-sha256 HASH_EXATO_DO_PLANO
"$MIA_BOOTSTRAP_PYTHON" "$MIA_INSTALL_ROOT/manager.py" --root "$MIA_INSTALL_ROOT" status
curl -fsS http://127.0.0.1:8123/health
curl -fsS http://127.0.0.1:8123/api/status
```

Antes de criar acesso, espere a versão da revisão escolhida e `configured:false`. No Linux, confira `loginctl show-user "$USER" -p Linger` antes de fechar a sessão; continuar sem login e após boot exige revisar e habilitar linger para a conta instalada. Isso é uma mudança do sistema separada do plano Mia, feita pelo operador, sem alterar serviços de outras contas. Depois feche o Terminal/SSH, abra novamente e repita a verificação: a Mia deve permanecer ativa. No Mac o LaunchAgent inicia depois do login; suspensão torna a instalação indisponível.

## 6. Acesso do Mac e iPhone ao servidor

Inicialmente mantenha a Mia em `127.0.0.1`. Um túnel SSH temporário permite preparar a instalação antes de publicar HTTPS, se a porta local estiver livre:

```bash
ssh -N -L 8124:127.0.0.1:8123 "$MIA_SSH_TARGET"
```

Use `http://127.0.0.1:8124` no Mac durante essa preparação. A porta 8124 evita conflito com uma Mia local em 8123; confira que também está livre. Esse túnel é temporário e depende da sessão SSH aberta.

Para uso diário, prepare um endereço **HTTPS estável** conforme [ACCESS.md](ACCESS.md), com certificado confiável e serviço persistente. Escolha domínio/rede e topologia reais depois de conferir o proxy já existente. Uma rede privada existente, inclusive Tailscale, pode ser usada, mas não é obrigatória. Não redefina rotas compartilhadas de outros produtos. Não exponha uvicorn HTTP diretamente à internet.

Teste login e escrita autorizada pelo endereço HTTPS no Mac e no iPhone; teste fora do Wi-Fi do servidor e após fechar SSH. Confira cookie Secure, reinicialização, backup e recuperação. No iPhone, pode salvar esse endereço na tela de início; isso abre a mesma instalação e não cria cópia offline. Registrar “servidor” no onboarding não configura essa infraestrutura.

## 7. Recomeçar a experiência e liberar o piloto

Crie nome, senha e fuso; continue sem IA. Importe explicitamente um vault/export original, confira cobertura e exceções, escolha o trabalho atual e confirme suas fontes. A instalação antiga arquivada permanece separada. Hoje deve ajudar a retomar o foco com fontes conferíveis antes de configurar modelo; decisões e pendências sugeridas precisam de revisão de atualidade e autoria.

Só depois, se desejar, configure provedor, modelo e chave própria. A chave de um produto existente deve ser lida sem impressão e transferida por canal local seguro, ou trocada por uma chave Mia separada com limite no provedor. Não inclua chaves no script, Git, relatório ou convite. Conferir conexão gera chamada apenas quando autorizada; salvamento e importação não chamam IA. Assinaturas de chat e créditos de API são diferentes.

Antes dos convites, conclua [PILOT.md](PILOT.md) e registre evidências privadas:

- Importação do contexto real com contagem de fontes/omissões e conferência de papéis/datas.
- Hoje encontra o trabalho desejado e aponta fontes; sugestões não viram fatos/tarefas por conta própria.
- Linux disponível após SSH/boot, HTTPS real no Mac/iPhone e restauração ensaiada.
- Mac local disponível após fechar Terminal/login, suspensão/retomada, atualização e recuperação. Instalador sem Git/Python, assinatura e notarização continuam sendo um aceite próprio.
- Convidados escolhem local ou servidor, sem receber sua biblioteca/chave, e começam sem orientação durante o teste medido. Suporte é oferecido depois de registrar onde travaram.

Registre revisão instalada, tipo de instalação, tempo até primeiro resultado, ajuda necessária, cobertura e custo efetivamente observado. Não envie convites dizendo que o Mac dispensa instalação técnica até haver artefato assinado e validado em máquina limpa.
