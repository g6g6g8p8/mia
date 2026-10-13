# Decisão da licença da Mia

Status: **aguarda decisão do titular**. Este documento compara opções; não concede direitos sobre o código da Mia. Nenhuma licença do projeto foi adicionada ao pacote ou ao repositório. A publicação do repositório, os avisos de terceiros e a licença desses terceiros não substituem essa decisão.

| Opção | Reutilização e distribuição | Modificações | Patentes | Adequação |
| --- | --- | --- | --- | --- |
| [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | Permissiva, inclusive comercial, conservando licença/avisos | Podem permanecer fechadas; indicar arquivos alterados e manter avisos aplicáveis | Concessão explícita dos contribuidores, com condições de encerramento | Opção recomendada para um harness independente com ampla adoção e contribuição |
| [MIT](https://opensource.org/license/mit) | Permissiva, inclusive comercial; manter copyright e texto | Podem permanecer fechadas | Sem concessão explícita equivalente à Apache-2.0 | Texto curto e distribuição simples, se isso prevalecer na decisão |
| [AGPL-3.0-only](https://www.gnu.org/licenses/agpl-3.0.html) | Copyleft; disponibilizar fonte correspondente nas situações previstas | Obrigações também para interação remota com versões modificadas | Cláusulas próprias de patentes | Se o titular quiser exigir disponibilidade do código de derivações e serviços modificados; revisar compatibilidade da combinação distribuída |

Todas permitem uso comercial sob suas condições; nenhuma transforma automaticamente notas, backups, prompts privados, credenciais ou resultados dos usuários em código público. Marca, domínio, conteúdo de terceiros e condições de APIs são assuntos separados. A ausência de licença explícita não significa domínio público nem uma autorização geral de distribuição.

Antes de aplicar a decisão:

1. Confirmar o titular e a autorização sobre todas as contribuições e assets; a revisão de padrões privados não comprova titularidade.
2. Escolher um identificador e escopo: código, documentação e assets; tratar exceções expressamente.
3. Adicionar o texto oficial completo em `LICENSE`, com a atribuição confirmada quando aplicável. Para Apache, verificar necessidade de `NOTICE` próprio e manter avisos de terceiros; não inventar titulares.
4. Atualizar metadados/README/checklist e conferir que wheel, sdist e imagem carregam os textos. `THIRD_PARTY_NOTICES.md` continua separado e deve ser preservado.
5. Revisar a combinação efetivamente distribuída, em especial dependências nativas/Rust e pacotes do sistema se uma imagem for publicada. O inventário atual tem o escopo descrito em [DEPENDENCIES.md](DEPENDENCIES.md).

Próxima ação do titular: informar **Apache-2.0, MIT ou AGPL-3.0-only** (ou outra licença e seu escopo) e confirmar a atribuição. A comparação não declara que todas as possíveis combinações ou formas de distribuição já passaram por revisão jurídica.
