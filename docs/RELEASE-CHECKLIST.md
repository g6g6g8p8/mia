# Aceites de release — 12/10/2026

Estado: **alpha técnica, não release final para distribuição ampla**. Esta lista descreve evidência, não promessa.

| Marco | Comprovado | Falta para fechar |
| --- | --- | --- |
| M0 | Repositório independente; instalação vazia; revisão automatizada de padrões privados no histórico | Escolha e inclusão da licença; revisão de avisos das dependências |
| M1 | Instalação de pacote em Ubuntu 24.04 isolado e macOS; HTTP/assets, identidade, fontes, tarefas, busca e persistência | Instalação por participantes sem ajuda no M5 |
| M2 | Fontes delimitadas, ferramentas autorizadas, confirmação/idempotência, quotas/reserva/reconciliação; testes com simulador | Modelo real direto, qualidade/citações e custo observado com teto autorizado |
| M3 | Onboarding mobile, imports sintéticos, conflitos, organização/contexto revisáveis, configuração guiada de IA | Exports reais escolhidos pelos participantes; primeiro resultado útil e compreensão da revisão |
| M4 | Snapshot, integridade, restauração em outro diretório/máquina, migração e retorno à versão anterior, interrupção sem reenvio; teste offline no Ubuntu isolado | Automação de rede/HTTPS e atualização/backup; validação da rota remota sem VPN obrigatória; operação continua limitada a um proprietário e um worker |
| M5 | Roteiro do piloto e verificações técnicas reproduzíveis | 2–3 participantes, licença, benchmark real de qualidade/custo e decisão de release |

## Entradas necessárias para os aceites externos

- Provedor/modelo real e limite total de gasto autorizado para ensaio. Credencial configurada pelo proprietário na Mia; nunca enviada para o repositório. Assinatura de chat não é crédito de API.
- Participantes com suas próprias fontes e instalações. Sem necessidade de histórico do desenvolvedor; não enviar convites automaticamente.
- Licença de distribuição escolhida pelo titular antes de conceder permissões públicas de uso/modificação/distribuição.
- Para validar acesso remoto sem Tailscale: destino/domínio controlado pelo instalador e rota de entrada disponível, ou alternativa opcional escolhida. O assistente atual não provisiona essa infraestrutura.

## Critério de parada do piloto

Não divulgar economia percentual, custo fixo, compatibilidade universal de modelos/exports, instalação sem ajuda ou segurança certificada a partir de testes simulados. Falha que perde dados, duplica efeitos, envia contexto não autorizado ou excede limites bloqueia release até correção e novo ensaio do caso.

Conversa contínua, projetos estruturados e conectores adicionais permanecem evolução de produto; não entram como funcionalidades entregues nesta alpha.
