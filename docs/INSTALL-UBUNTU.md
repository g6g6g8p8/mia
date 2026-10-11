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

```bash
docker compose down
docker compose up -d --build
```

O volume `mia-data` permanece quando os containers são recriados. Não execute `docker compose down -v` se quiser preservar os dados.

## Backup do volume

A interface oferece uma exportação JSON das áreas e tarefas. A restauração automática dessa exportação ainda não está implementada.

Para uma cópia operacional completa do piloto, pare o serviço e copie o conteúdo do volume `mia-data` com uma ferramenta apropriada ao seu ambiente. Valide a restauração em outra máquina antes de considerar o backup confiável.

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

