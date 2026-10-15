# Mia
![Ícone da Mia — gatinha em estilo ASCII](assets/mia-icon.svg)

**IA pessoal com seu contexto de trabalho, sob seu controle.**

Mia é um projeto de IA pessoal para reunir notas, conversas e decisões e ajudar você a retomar o trabalho com fontes. O código é público; seus arquivos e conversas ficam na instalação que você escolhe, separados do repositório.

Você escolhe guardar o contexto no próprio computador ou em um servidor. A **Mia Demo para Mac** tem janela própria, instalação/conexão guiadas e infraestrutura de convites/atualizações. A a14 amplia operação e distribuição do beta; a distribuição para convidados aguarda validação integrada, assinatura/notarização e aceites reais. Mac e iPhone podem acessar o mesmo backend quando a rede estiver preparada; instalação local depende do computador disponível. Modelos/APIs são opcionais. Importar e buscar funcionam sem IA.

## Status

**0.2.0a14 — cliente Mac, operação do servidor e distribuição privada do beta.** O app usa SwiftUI/AppKit + WKWebView, runtime incluído, destinos próprios local/SSH/HTTPS e atualização do cliente via Sparkle. O onboarding dentro da janela começa pelas fontes, segue para foco confirmado e Hoje; IA é opcional. A navegação é Hoje, Conversas, Biblioteca e Ajustes. Atualização, snapshot e recuperação do backend têm planos e confirmação separados, também no servidor gerenciado. [Implementação, evidência e limites](docs/MAC-DEMO-IMPLEMENTATION.md).

O novo fluxo aceita ZIP, pasta pelo navegador compatível, Markdown/texto e formatos específicos de exports ChatGPT/Claude. Não pede primeira área nem chave de IA para começar. Relatórios distinguem material reconhecido, ignorado, não selecionado, duplicado e com erro. Arquivos do Drive entram depois de baixados/exportados; `.gdoc` é um link, não o conteúdo do documento. Não existe conector recorrente Drive, app nativo iPhone ou sync offline.

Conversas persistem nesta instalação. Contexto recuperado, histórico reautorizado e foco opcional têm limites; fontes pausadas e material ainda em revisão ficam fora dos novos pedidos. Consultar toda a biblioteca não autoriza criar tarefas em uma área por inferência. Propostas e organização/personalização assistidas continuam exigindo revisão; Sobre mim e objetivo pessoal são opt-in em cada pedido.

O cliente nativo cria instalação local com serviço de usuário e protege a criação do primeiro proprietário por autorização privada. No servidor, o assistente exige Ubuntu 24.04 amd64 com SSH/serviço persistente preparados e inclui o runtime Linux verificado; conecta por túnel gerido ou HTTPS existente. O launcher antigo de navegador e a [instalação administrativa](docs/INSTALL-BACKGROUND.md) continuam para desenvolvimento/suporte. [Roadmap](docs/ROADMAP.md) separa código implementado de assinatura, publicação e testes reais ainda pendentes.

A hospedagem escolhida para convites e atualizações é **Vercel, no plano gratuito**, com metadados duráveis separados das bibliotecas pessoais. O kit preparatório foi publicado em [mia-beta-distribution.vercel.app](https://mia-beta-distribution.vercel.app), com resposta 503 deliberada enquanto o beta não está liberado. Stores Blob estão preparados; Upstash e aceites finais permanecem pendentes. Nenhum convite real foi emitido. O CI nativo aprovou os dois pacotes internos, incluindo WebKit e launchd reais. Assinatura Apple e aceites nos aparelhos finais continuam pendentes. [Publicação do beta](docs/BETA-PUBLICATION.md).

O [plano de experiência](docs/EXPERIENCE-PLAN.md) separa implementação, testes sintéticos e aceites com pessoas/fontes reais. Passar um vault sintético não demonstra compatibilidade com qualquer vault ou export nem primeiro valor sem ajuda. O código, documentação e assets próprios usam [Apache-2.0](LICENSE), conforme [NOTICE](NOTICE); dependências conservam suas licenças e dados pessoais permanecem privados. Economia e release ampla continuam pendentes.

O [ensaio histórico com DeepSeek via OpenRouter](docs/REAL-MODEL-VALIDATION.md) registrou 17 chamadas sintéticas e US$ 0.0045882598 informados pelo provedor. Não certifica a qualidade geral da nova jornada nem economia. Em Ajustes → IA, verificar conexão consulta apenas o catálogo, sem gerar texto ou enviar fontes; não comprova saldo, ferramentas ou qualidade.

## O que o Mia deve oferecer
- Onboarding para trazer o próprio contexto, conferir cobertura e chegar a um primeiro resultado útil.
- Contexto recuperado conforme a tarefa, com indicação de origem.
- Memória persistente, inspecionável, editável e exportável pelo usuário.
- Conversas e execuções que podem ser retomadas após reinício.
- Ferramentas com contratos, permissões e resultados verificáveis.
- Propostas de ação revisadas antes de executar alterações.
- Escolha de modelos locais ou externos, com credenciais próprias.
- Limites de uso, estimativas e registros de custo.
- Experiência alinhada à proposta: Hoje, Conversas, Biblioteca e Ajustes, com busca transversal.

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
A instalação não deve exigir uma conta central de contexto, hospedagem proprietária ou provedor específico de IA. O convite da demo controla os downloads e as atualizações oficiais; sua autorização fica no Keychain do Mac. Depois de instalada, a biblioteca não depende do serviço de convites. Apache-2.0 permite compilar e distribuir o código público sem convite.

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

## Instalação técnica atual
Os passos abaixo são administrativos, para desenvolvimento/suporte da alpha. O percurso dos convidados será o aplicativo descrito em [MAC-DEMO](docs/MAC-DEMO.md), quando seu artefato estiver aprovado. Para a instalação técnica Ubuntu atual, veja [Instalação no Ubuntu](docs/INSTALL-UBUNTU.md).

```bash
cp .env.example .env
docker compose up -d --build
```

Por padrão, a interface abre somente em `http://127.0.0.1:8123`.

A [operação nativa gerenciada](docs/OPERATIONS.md) oferece versões separadas, atualização explícita com snapshot e recuperação/retorno em dados novos. O modo manual e Docker continuam disponíveis. Ajustes → Operação e atualização mostra versão/estado; Ajustes → Acesso prepara um plano HTTPS revisável com recuperação local. Ativar serviço e publicar domínio, rota ou portas são passos administrativos explícitos, separados da importação.

Propostas de tarefa podem ser editadas antes de confirmar. A proposta original e a escolha aplicada ficam no histórico/exportação; repetir confirmação não cria outra tarefa.

## Documentação
- [Contrato da Mia Demo — aplicativo Mac por convite](docs/MAC-DEMO.md)
- [Implementação a14, build e aceites da distribuição](docs/MAC-DEMO-IMPLEMENTATION.md)
- [Publicação privada do beta na Vercel](docs/BETA-PUBLICATION.md)
- [Roadmap da demonstração e próximas atualizações](docs/ROADMAP.md)
- [Roteiro de limpeza e instalação do zero](docs/CLEAN-INSTALL.md)
- [Plano de produto e execução](docs/PLAN.md)
- [Contrato do harness](docs/HARNESS.md)
- [Ícone e identidade](docs/BRAND.md)
- [Instalação no Ubuntu](docs/INSTALL-UBUNTU.md)
- [Validação do M1](docs/VALIDATION.md)
- [Configurar IA e limites do M2](docs/AI.md)
- [Instalação nativa no Mac ou Linux](docs/INSTALL-NATIVE.md)
- [Uso sem Terminal diário, serviço e migração manual](docs/INSTALL-BACKGROUND.md)
- [Roteiro do piloto com usuários](docs/PILOT.md)
- [Licença Apache-2.0 e escopo](docs/LICENSE-OPTIONS.md)
- [Dependências e avisos preservados na distribuição](docs/DEPENDENCIES.md)
- [Onboarding e importação de conhecimento](docs/ONBOARDING.md)
- [Backup e restauração](docs/BACKUP.md)
- [Acesso local e remoto](docs/ACCESS.md)
- [Aceites e pendências para release](docs/RELEASE-CHECKLIST.md)

## Desenvolvimento
O histórico deste repositório começa em um commit novo. Não contém dados de usuários, conversas, vaults ou histórico de outros projetos.

A evolução será validada por entregas completas: instalação → onboarding → contexto → resposta → proposta → confirmação → persistência → restauração.

