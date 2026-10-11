# Validação do M1

Registro de validação reproduzível do protótipo instalável, sem dados pessoais.

## Ambiente

- Data: 11/10/2026
- Host: Ubuntu, arquitetura x86_64
- Docker Engine: 29.1.3
- Docker Compose: 2.40.3
- Revisão testada: `81e27fab01225da15c45bfdbdfaf4b47cd6e9836`
- Exposição: somente `127.0.0.1:8123`

## Resultado

| Verificação | Resultado |
| --- | --- |
| Build da imagem a partir do repositório | Aprovado |
| Healthcheck do contêiner | Aprovado |
| Instalação começa sem proprietário | Aprovado |
| Acesso anônimo a dados recebe HTTP 401 | Aprovado |
| Onboarding e sessão local | Aprovado |
| Criação e listagem de tarefa | Aprovado |
| Priorização em Hoje | Aprovado |
| Busca por tarefa | Aprovado |
| Exportação ZIP e teste de integridade | Aprovado |
| Dados preservados após reinício | Aprovado |
| Remoção dos dados fictícios e retorno ao estado vazio | Aprovado |
| Ocupação do disco após o teste | 68% |

## Procedimento resumido

1. Clonar o repositório em um diretório novo.
2. Copiar `.env.example` para `.env`.
3. Executar `docker compose up -d --build`.
4. Aguardar o estado `healthy` e consultar `/health` e `/api/status`.
5. Confirmar HTTP 401 em `/api/me` sem sessão.
6. Concluir o onboarding com dados descartáveis.
7. Criar uma tarefa e verificar Hoje, Busca e exportação.
8. Reiniciar o serviço e confirmar a permanência da tarefa.
9. Remover somente o volume descartável do piloto e subir novamente.
10. Confirmar `configured: false` na nova instalação vazia.

Este ensaio valida o aceite instalável do M1. Ele não valida ainda o harness de IA, restauração em outra máquina, atualização automática, uso concorrente ou segurança para exposição direta à internet.

## Segunda rodada — macOS independente e M2 inicial

Em 11/10/2026, clone novo em macOS ARM64, Python 3.12.13, ambiente virtual e dados isolados. Instaladas as dependências de `requirements.lock`, sem depender do primeiro host Ubuntu.

- 17 testes automatizados passaram em Linux de desenvolvimento e no Mac.
- Chromium headless executou onboarding → tarefa → área → busca → IA desativada → prévia de contexto → viewport móvel de 390 px → concluir tarefa → sair/entrar, sem erro JavaScript.
- Outro fluxo Chromium usou o adaptador HTTP real contra um servidor de respostas simuladas: proposta sem gravação → recarregar → confirmar → tarefa única → nova proposta → recusar. A chamada não saiu da máquina de teste.
- Testes cobrem concorrência, aprovação idempotente, área não autorizada, ferramenta desconhecida, resposta malformada, falha do provedor, cota diária, consentimento e execução interrompida sem repetição automática.
- Correções motivadas por evidência: formulário perdia referência após `await`, tentativa de login sofria rollback, logout escondido no mobile, comparação de data UTC e busca com resposta atrasada.

Não foram validados qualidade com modelo real, custo monetário, benchmark de economia, restauração em segunda máquina ou experiência sem ajuda com usuários. A instalação independente não equivale a teste de restauração. Há um aviso de depreciação não bloqueante no TestClient/AnyIO.
