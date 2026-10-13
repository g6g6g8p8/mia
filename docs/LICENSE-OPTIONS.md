# Licença da Mia — Apache-2.0

13/10/2026. O proprietário delegou a escolha ao assistente e a recomendação **Apache-2.0** foi aplicada. [LICENSE](../LICENSE) contém os termos completos; [NOTICE](../NOTICE) registra a atribuição coletiva “Mia contributors” e o escopo.

A licença cobre código, documentação e assets originais da Mia neste repositório. Dependências e avisos de terceiros mantêm as condições e atribuições upstream. Notas, imports, conversas, credenciais, backups, resultados privados e conteúdo de serviços não são licenciados como código público da Mia.

## Motivo da escolha

Apache-2.0 permite uso, modificação e distribuição, inclusive comercial, com preservação das condições de licença e avisos aplicáveis. Inclui concessão explícita de patentes pelos contribuidores e condições de encerramento dessa concessão. É adequada à proposta de um produto independente, self-hosted e aberto a adoção/contribuição.

Derivações podem permanecer fechadas; esta escolha não exige abrir serviços modificados. Marca/domínio não recebem licença automática por essa licença de software. Não há promessa de custo ou economia associada à licença.

## Alternativas consideradas

| Licença | Condição central | Motivo para não escolher nesta rodada |
| --- | --- | --- |
| MIT | Permissiva, texto curto e preservação do aviso | Sem concessão explícita de patentes equivalente |
| AGPL-3.0-only | Copyleft, com obrigações para interação remota com versões modificadas | A proposta atual prioriza adoção permissiva; exigir abertura dessas derivações seria outra decisão de produto |

As alternativas também permitem uso comercial sob suas condições. Elas não foram aplicadas à Mia.

## Preservação e distribuição

LICENSE e NOTICE entram em wheel, sdist, contexto Docker e empacotador Mac. O verificador confere os próprios textos e preserva os 279 textos originais de terceiros mais seus inventários/aviso geral. Metadados Python usam formato compatível com setuptools 75 e identificam Apache Software License.

O texto completo foi obtido por HTTPS do repositório oficial Apache e conferido com a forma canônica SPDX; não foi usada uma licença vendorizada com copyright de outro titular. A atribuição coletiva não inventa nome de empresa, endereço ou identidade legal.

Distribuir runtime/binários, especialmente pacote Mac e imagem de sistema, ainda exige conferir os avisos/componentes do artefato concreto. Aplicar Apache à Mia não relicencia certifi, Python, bibliotecas nativas ou sistema operacional. O escopo dessa revisão está em [DEPENDENCIES.md](DEPENDENCIES.md).
