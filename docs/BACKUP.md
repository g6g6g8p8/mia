# Backup e restauração

Parte inicial do M4. Snapshot consistente de SQLite, incluindo proprietário, áreas, tarefas, fontes, lotes revisáveis, objetivo e execuções. Testado com dados sintéticos do Linux para o Mac. Não copiar apenas um arquivo SQLite ativo ignorando o WAL.

## Instalação nativa

Na pasta do aplicativo, com nome de destino novo:

```bash
mkdir -p backups
.venv/bin/python -m mia.backup backup backups/mia-snapshot.db
```

Usa `MIA_DATA_DIR` ou `./data`, cria arquivo `0600` e não sobrescreve backup existente. Proteja-o: contém conhecimento pessoal e hash de senha. Configuração e chaves de IA não são incluídas.

Restauração em diretório **novo e vazio**:

```bash
.venv/bin/python -m mia.backup verify backups/mia-snapshot.db
.venv/bin/python -m mia.backup restore backups/mia-snapshot.db ./restored-data
MIA_DATA_DIR=./restored-data .venv/bin/uvicorn mia.app:app --host 127.0.0.1 --port 8123
```

Valida integridade e estrutura, recusa destino com dados e invalida sessões antigas. Entre com a senha do proprietário restaurado e reconfigure IA. Gerações interrompidas não são reenviadas; propostas pendentes permanecem.

`verify` lê o arquivo sem restaurar nem mostrar conteúdo pessoal, verificando integridade SQLite, tabelas essenciais e referências. Não substitui ensaio de restauração nem certifica compatibilidade com versões futuras. A restauração prepara uma cópia temporária privada e só publica o banco após invalidar sessões e validar a cópia; falhas não deixam um banco parcialmente restaurado. A publicação exige suporte a hard links no sistema de arquivos de destino. Backups incompletos por falha também são removidos.

## Docker

```bash
docker compose exec mia python -m mia.backup backup /data/mia-snapshot.db
docker compose cp mia:/data/mia-snapshot.db ./mia-snapshot.db
```

Use nome novo por snapshot e guarde cópia fora do volume. Restaure no diretório vazio escolhido pelo comando Python acima, ou em instalação nativa temporária; para Docker, configure deliberadamente o volume da nova instalação apontando para esses dados. Assistente de restauração de volume ainda não existe.

## Atualização e recuperação — procedimento M4

1. Registre a versão/commit atual e o comando de inicialização da sua instalação. Não atualize durante uma execução de IA.
2. Gere um backup com nome novo e use `verify`. Guarde cópia fora da máquina. Preserve separadamente configurações locais e credenciais, sem colocá-las no Git.
3. Pare a Mia pelo mecanismo usado na instalação, atualize para o commit escolhido e reinstale/reconstrua o pacote. Mantenha o mesmo diretório de dados. Não use múltiplos workers.
4. Inicie e confira `/api/status`, login, uma fonte/tarefa conhecida e o acesso pelo dispositivo habitual.
5. Se falhar, pare a versão nova. Restaure o backup em diretório vazio e execute a versão anterior apontando para esse diretório. Não execute código antigo sobre banco já migrado e não sobrescreva o banco original. Reconfigure a IA e as preferências de acesso.

Este é um procedimento manual. Instalador de atualização, reversão automática e ensaio de upgrade entre versões em Ubuntu limpo continuam pendentes; o backup restaurado não contém alterações feitas depois do snapshot.

### Ensaio reproduzível sem dados reais

Em um ambiente de desenvolvimento com dependências instaladas, execute:

```bash
python scripts/upgrade_smoke.py --baseline-ref 2d43f085c8e9388202ec3d3914f1da20a4a14b9a
```

O commit informado corresponde à 0.2.0a3 do repositório público. O script extrai esse commit e o `HEAD` em diretórios temporários, cria dados sintéticos, atualiza o banco, reinicia, restaura o snapshot em outro diretório e verifica a versão antiga sobre o banco restaurado. Não aponta para dados da instalação, não abre serviço de rede e não chama IA. Exige Git e Python 3.12+ com as dependências de desenvolvimento. O teste usa código dos commits, não alterações ainda não commitadas.

Verifica identidade, tarefa, fonte, objetivo, migração de contexto, sessão invalidada após restauração e reserva de custo preservada após interrupção. Não substitui build de pacote, instalação de dependências em máquina limpa nem teste com falha elétrica real.

## Limitações atuais

Somente backups locais confiáveis. Sem criptografia, agendamento, rotação, restauração do ZIP exportado ou atualização automática. O ensaio entre máquinas usou dados sintéticos; não restaurou dados reais do proprietário.
