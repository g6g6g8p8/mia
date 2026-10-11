# Mia
![Ícone da Mia — gatinha em estilo ASCII](assets/mia-icon.svg)

**IA pessoal com contexto, ferramentas e controle de custos.**

Mia é um projeto de harness para IA pessoal: a estrutura que reúne memória, contexto, ferramentas e regras de execução para tornar modelos de IA úteis no dia a dia.

O usuário instala o Mia em seu computador ou servidor Ubuntu e acessa pelo navegador. Escolhe os modelos e as integrações que quer usar; seus dados permanecem sob seu controle.

## Status
O M1 é um protótipo executável, validado em Docker sobre Ubuntu e em instalação Python independente no macOS, com fluxo de navegador automatizado. Inclui onboarding local, acesso do proprietário, áreas, tarefas, Hoje, Busca, exportação e persistência SQLite.

O **M2** acrescenta pedidos independentes com contexto de uma área, adaptador opcional Chat Completions, propostas confirmadas, histórico e orçamento estimado com reserva. O **M3 inicial** oferece onboarding retomável, objetivo declarado, importação local com revisão, busca de fontes e configuração de IA pela interface. Markdown, texto e ZIP são suportados; adaptadores de conversas ChatGPT/Claude são experimentais e reconhecem formatos específicos.

A integração foi testada com um provedor simulado local: **não há ainda validação de qualidade ou cobrança com um modelo real**. Há backup SQLite e restauração por comando em instalação vazia, testada do Linux para o Mac. Conversa contínua, personalização inferida, conectores, atualização/backup automáticos e benchmark de economia continuam pendentes.

A primeira versão será validada com poucos usuários piloto. O repositório é público por decisão do proprietário; a licença específica de uso e distribuição ainda está pendente.

## O que o Mia deve oferecer
- Onboarding para configurar objetivos, áreas, fontes e permissões.
- Contexto recuperado conforme a tarefa, com indicação de origem.
- Memória persistente, inspecionável, editável e exportável pelo usuário.
- Conversas e execuções que podem ser retomadas após reinício.
- Ferramentas com contratos, permissões e resultados verificáveis.
- Propostas de ação revisadas antes de executar alterações.
- Escolha de modelos locais ou externos, com credenciais próprias.
- Limites de uso, estimativas e registros de custo.
- Central de comando com Hoje, Áreas, Planejamento, Busca, Inteligência e Sistema.

Exemplo de uso: preparar uma reunião a partir de documentos autorizados, apontar as fontes e sugerir próximos passos; o usuário revisa antes de registrar uma tarefa.

## Como o custo será controlado
A meta é custo baixo comprovado em tarefas reais:
- Regras determinísticas para trabalho que não exige geração.
- Busca seletiva para enviar apenas contexto relevante ao modelo.
- Modelos locais ou econômicos quando adequados à tarefa.
- Modelos mais caros somente com política explícita.
- Limites de contexto, saída, duração, passos e tentativas.
- Orçamento por execução e período.
- Registro de tokens, modelo e uso; custo estimado separado do custo confirmado.
- Pausa quando o orçamento ou o limite de execução for atingido.

A primeira versão não promete valor mensal fixo. IA local também tem custo de hardware, energia e operação. APIs externas seguem as condições e preços do provedor escolhido.

## Independência
A instalação não deve exigir uma conta do projeto, um domínio central, um serviço proprietário de hospedagem ou um provedor específico de IA.

O núcleo precisa funcionar sem IA e, após instalado, sem internet. Recursos de IA local exigem um motor e modelo compatíveis. Conectores e modelos externos precisam de rede e autorização do usuário.

Assinatura de um aplicativo de chat não será tratada como crédito de API.

## Dados e controle
- Instalação vazia por padrão.
- Importação explícita, separada do código do produto.
- Conteúdo local em formatos abertos.
- Credenciais fora do código, do navegador e do Git.
- Histórico e índices restritos ao proprietário autorizado.
- Backup e restauração testados em outra máquina.
- Ações com evidência, proveniência e prevenção de duplicação.

## Instalação
O alvo inicial é Ubuntu em servidor ou computador pessoal. Veja [Instalação no Ubuntu](docs/INSTALL-UBUNTU.md).

```bash
cp .env.example .env
docker compose up -d --build
```

Por padrão, a interface abre somente em `http://127.0.0.1:8123`.

## Documentação
- [Plano de produto e execução](docs/PLAN.md)
- [Contrato do harness](docs/HARNESS.md)
- [Ícone e identidade](docs/BRAND.md)
- [Instalação no Ubuntu](docs/INSTALL-UBUNTU.md)
- [Validação do M1](docs/VALIDATION.md)
- [Configurar IA e limites do M2](docs/AI.md)
- [Instalação nativa no Mac ou Linux](docs/INSTALL-NATIVE.md)
- [Roteiro do piloto com usuários](docs/PILOT.md)
- [Onboarding e importação de conhecimento](docs/ONBOARDING.md)
- [Backup e restauração](docs/BACKUP.md)

## Desenvolvimento
O histórico deste repositório começa em um commit novo. Não contém dados de usuários, conversas, vaults ou histórico de outros projetos.

A evolução será validada por entregas completas: instalação → onboarding → contexto → resposta → proposta → confirmação → persistência → restauração.

