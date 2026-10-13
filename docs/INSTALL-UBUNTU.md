# Instalação no Ubuntu

Status: primeira versão técnica para pilotos. Use em uma máquina de teste antes de adotar para dados importantes.

## Requisitos

- Ubuntu com Docker Engine e o plugin Docker Compose.
- Acesso ao terminal.
- Porta local 8123 disponível.

## Iniciar

Na pasta do repositório:

```bash
cp .env.example .env
docker compose up -d --build
```

Abra `http://127.0.0.1:8123` no navegador da própria máquina.

No primeiro acesso, crie o proprietário e a primeira área. Não há conta externa, conteúdo de demonstração ou IA configurada.

## Parar e atualizar

O procedimento abaixo mantém o modo Docker existente. Para uma instalação nativa nova, veja [OPERATIONS.md](OPERATIONS.md), com atualização consciente e recuperação em dados separados. O gerenciador nativo não controla containers nem volumes Docker.

Primeiro faça e verifique um snapshot conforme [BACKUP.md](BACKUP.md), guarde-o fora do volume e registre o commit atual. Aguarde qualquer geração em andamento. Não apague o volume.

```bash
docker compose down
git pull --ff-only
docker compose up -d --build
```

O volume `mia-data` permanece quando os containers são recriados. Não execute `docker compose down -v` se quiser preservar os dados.

Confira `docker compose ps`, `/api/status`, login e uma fonte/tarefa conhecida. Em falha, siga a restauração em diretório vazio descrita em BACKUP; não execute versão antiga diretamente sobre banco migrado.

## Verificação isolada para mantenedores

```bash
bash scripts/clean_ubuntu.sh 2d43f085c8e9388202ec3d3914f1da20a4a14b9a
```

Requer Docker e Git no host. Cria um contêiner Ubuntu 24.04 com Python/dependências novos, instala o pacote, desconecta a rede e executa os testes, atualização/restauração e inicialização HTTP com assets. Usa dados sintéticos e remove o contêiner/diretório temporário ao terminar; a imagem Ubuntu pode permanecer no cache. Consome rede durante instalação e até 1 GB de memória no contêiner. Não usa volume de uma instalação existente.

Se a rede do runner exigir uma CA que não está no Ubuntu novo, forneça explicitamente `MIA_VALIDATION_WHEELHOUSE=/caminho/dos/wheels-verificados`; o runner monta o cache somente leitura e instala sem consultar índice. Inclua pins de `requirements.lock`, pytest 8.3.4, pip 25.0.1, setuptools 75.8.0 e wheel 0.45.1, além das dependências de teste. O cache precisa corresponder à arquitetura/Python do container. Não use `--trusted-host` ou desative TLS para contornar falhas de confiança.

Nesse modo, o runner também executa o lifecycle do gerenciador nativo em instalações temporárias, com falha/recuperação/rollback. Para construir a imagem do produto usando wheels verificados, sem mudar o Dockerfile, use `scripts/build_offline_image.py --help`: o helper prepara um contexto público temporário, confere hashes e instala sem rede. A imagem base ainda precisa estar acessível ou no cache; isso não é publicação de imagem nem instalação de rede/HTTPS.

Isso valida um ambiente de usuário Ubuntu isolado, não uma instalação completa de sistema operacional, systemd, roteador, certificado público ou operação por usuário sem ajuda. O pacote Docker do produto usa a base definida no Dockerfile; o Ubuntu aqui é o ambiente de teste da instalação nativa.

## Backup do volume

A interface exporta JSON de áreas, tarefas, fontes, objetivo e execuções. Restauração desse ZIP ainda não existe; há snapshot consistente SQLite e restauração por comando em [BACKUP.md](BACKUP.md).

Chaves e configuração de IA precisam ser recriadas após restaurar. Snapshot sintético foi restaurado entre Linux e Mac. Agendamento e rotação locais podem ser habilitados em Sistema → Backups enquanto a Mia roda; guarde cópia fora do volume.

## Acesso remoto

Por padrão, a porta fica ligada apenas a `127.0.0.1`. Não altere `MIA_BIND` para `0.0.0.0` e exponha diretamente na internet.

Para acesso remoto, use uma rede privada ou um proxy HTTPS configurado conscientemente. Com HTTPS, defina:

```dotenv
MIA_COOKIE_SECURE=true
```

## Diagnóstico

```bash
docker compose ps
docker compose logs --tail=100 mia
curl http://127.0.0.1:8123/health
```

