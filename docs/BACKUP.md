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
.venv/bin/python -m mia.backup restore backups/mia-snapshot.db ./restored-data
MIA_DATA_DIR=./restored-data .venv/bin/uvicorn mia.app:app --host 127.0.0.1 --port 8123
```

Valida integridade e estrutura, recusa destino com dados e invalida sessões antigas. Entre com a senha do proprietário restaurado e reconfigure IA. Gerações interrompidas não são reenviadas; propostas pendentes permanecem.

## Docker

```bash
docker compose exec mia python -m mia.backup backup /data/mia-snapshot.db
docker compose cp mia:/data/mia-snapshot.db ./mia-snapshot.db
```

Use nome novo por snapshot e guarde cópia fora do volume. Restaure no diretório vazio escolhido pelo comando Python acima, ou em instalação nativa temporária; para Docker, configure deliberadamente o volume da nova instalação apontando para esses dados. Assistente de restauração de volume ainda não existe.

## Limites

Somente backups locais confiáveis. Sem criptografia, agendamento, rotação, restauração do ZIP exportado ou atualização automática. O ensaio entre máquinas usou dados sintéticos; não restaurou dados reais do proprietário.
