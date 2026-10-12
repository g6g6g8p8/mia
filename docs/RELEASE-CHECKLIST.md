# Aceites de release — 12/10/2026

Estado: **alpha técnica, não release final para distribuição ampla**. Esta lista descreve evidência, não promessa.

Atualização 0.2.0a9: consulta, ação, organização e personalização com modelo real via OpenRouter validadas em material sintético. Comparação de contexto executada e falha de busca corrigida. Total acumulado: 17 chamadas, US$ 0.0045882598 informado pelo provedor, dentro do teto total US$ 1. [Resultados e limitações](REAL-MODEL-VALIDATION.md). Não fecha provedor direto, economia, fontes reais ou piloto externo.

Ensaio completo em Ubuntu 24.04.5 isolado aprovado: instalação nova, 59 testes sem rede, migração, reinício, restauração e HTTP/assets do pacote instalado. Evidência reproduzível em VALIDATION.md e `scripts/clean_ubuntu.sh`. Protocolo em [BENCHMARK.md](BENCHMARK.md), com ensaio sintético executado. A versão atual passou 66 testes no Linux; a evidência Ubuntu acima pertence à versão anterior.

| Marco | Comprovado | Falta para fechar |
| --- | --- | --- |
| M0 | Repositório independente; instalação vazia; revisão automatizada de padrões privados no histórico | Escolha e inclusão da licença; revisão de avisos das dependências |
| M1 | Instalação de pacote em Ubuntu 24.04 isolado e macOS; HTTP/assets, identidade, fontes, tarefas, busca e persistência | Instalação por participantes sem ajuda no M5 |
| M2 | Fontes delimitadas, ferramentas autorizadas, confirmação/idempotência, quotas/reserva/reconciliação; testes com simulador e modelo real via gateway, citações e custo observado | Provedor direto; qualidade representativa com participantes |
| M3 | Onboarding mobile, imports sintéticos, conflitos, organização/contexto revisáveis, configuração guiada de IA; organização e contexto aprovados com modelo real e fontes sintéticas | Exports reais escolhidos pelos participantes; primeiro resultado útil e compreensão da revisão |
| M4 | Snapshot, rotina local opcional de 24 horas com retenção/download, integridade, restauração em outro diretório/máquina, migração e retorno à versão anterior, interrupção sem reenvio; teste offline no Ubuntu isolado | Automação de rede/HTTPS e atualização; cópia fora da máquina; validação da rota remota sem VPN obrigatória; operação continua limitada a um proprietário e um worker |
| M5 | Roteiro do piloto e verificações técnicas reproduzíveis | 2–3 participantes, licença, benchmark representativo de qualidade/custo e decisão de release |

## Entradas necessárias para os aceites externos

- Para aceite sem gateway: provedor direto escolhido e credencial própria configurada na Mia. O ensaio atual via gateway já tem autorização total de US$ 1; não exige nova autorização dentro desse teto. Credenciais nunca entram no repositório.
- Participantes com suas próprias fontes e instalações. Sem necessidade de histórico do desenvolvedor; não enviar convites automaticamente.
- Licença de distribuição escolhida pelo titular antes de conceder permissões públicas de uso/modificação/distribuição.
- Para validar acesso remoto sem Tailscale: destino/domínio controlado pelo instalador e rota de entrada disponível, ou alternativa opcional escolhida. O assistente atual não provisiona essa infraestrutura.

## Critério de parada do piloto

Não divulgar economia percentual, custo fixo, compatibilidade universal de modelos/exports, instalação sem ajuda ou segurança certificada a partir de testes simulados. Falha que perde dados, duplica efeitos, envia contexto não autorizado ou excede limites bloqueia release até correção e novo ensaio do caso.

Conversa contínua, projetos estruturados e conectores adicionais permanecem evolução de produto; não entram como funcionalidades entregues nesta alpha.
