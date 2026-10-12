# Dependências e escopo da revisão

Revisão técnica em 12/10/2026: 21 distribuições Python fixadas em `requirements.lock`, metadados e 24 arquivos de licença fornecidos pelos wheels instalados no Linux x86_64. Foram preservados também cinco avisos do libuv fornecido no sdist de uvloop 0.23.0 e o texto completo da MPL-2.0 para certifi: **30 textos**, sem alterar os originais. O inventário legível por máquina e os SHA256 estão em `THIRD_PARTY_LICENSES/inventory.json`; a tabela está em [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

O sdist de uvloop foi obtido do endereço de artefato publicado no índice PyPI, com HTTPS verificado e SHA256 comparado ao publicado pelo índice (`28d160f51ab4da3b187063652e643dea6831072add4adc1e6d62afbe73b6be27`). O libuv tem MIT, trechos BSD-2-Clause e ISC; os comentários iniciais de atribuição/licença de `tree.h` e `inet.c` foram copiados, sem importar código. A licença de documentação upstream (CC-BY-4.0) foi preservada por completude do conjunto, sem distribuir a documentação do libuv. O endereço oficial da Mozilla foi bloqueado pelo proxy (403); o texto MPL completo veio do arquivo de licenças da imagem Debian, com origem e hash registrados. O aviso fornecido por certifi foi mantido integralmente.

## O que está incluído

- Runtime direto: FastAPI, HTTPX e Uvicorn com extras `standard`.
- Dependências transitivas Python do lock, incluindo validação, transporte HTTP, certificados, YAML, tipagem e extras nativos do Uvicorn.
- Avisos vendorizados publicados por httptools (`http-parser` e `llhttp`) e libuv do uvloop, inclusive textos MIT/Apache-2.0 oferecidos upstream.
- Preservação dos textos no repositório, wheel e sdist; Docker copia o mesmo conjunto antes de instalar a Mia. O wheel da Mia declara dependências, não embute seus binários.

MIT/BSD requerem preservar os avisos e textos aplicáveis. Apache inclui condições de atribuição, arquivos modificados e `NOTICE` quando fornecido. PSF conserva seu acordo e histórico. MPL aplica obrigações aos arquivos cobertos, sem automaticamente relicenciar os arquivos próprios e separados da Mia; se certifi for modificado ou redistribuído em uma imagem, cumprir acesso à fonte correspondente e avisos. A tabela reproduz identificadores declarados ou confirmados nos textos; não concede licença à Mia.

## Limites e próximos passos

Este inventário **não é uma liberação jurídica de todos os artefatos**. Ele não enumera toda a árvore de crates Rust incorporada nos wheels de `pydantic-core`/`watchfiles`, nem pacotes do Python, da imagem base ou do sistema operacional. A inspeção dos sdists dessas duas distribuições encontrou apenas o texto de licença próprio; isso não prova ausência de componentes transitivos incorporados. Dependências de desenvolvimento (`pytest`, seus plugins, empacotador) também têm avisos próprios e não fazem parte do runtime publicado pela Mia.

Para distribuir imagens/binários que incluam essas bibliotecas, gerar inventário do artefato exato com plataforma/digests e conferir avisos/fontes de todos os componentes incorporados, inclusive sistema operacional e crates, antes de publicação ampla. As dependências não são código extraído de um projeto pessoal; nenhum histórico ou dado privado foi copiado para esta revisão. Licença própria e revisão de titularidade continuam pendentes: [opções concretas](LICENSE-OPTIONS.md).

Uma troca de versão, extras, plataforma ou imagem exige nova revisão dos artefatos correspondentes. Não atualizar o JSON apenas para passar a checagem; obter os textos da nova versão, preservar atribuições e registrar sua origem/hash. Em plataformas que omitam extras nativos, conferir o subconjunto instalado sem declarar o ensaio Linux como evidência de instalação no Mac.

## Conferência reproduzível

```bash
python scripts/check_distribution.py --installed
python -m build --outdir /tmp/mia-dist
python scripts/check_distribution.py --archive /tmp/mia-dist/<pacote>.whl --archive /tmp/mia-dist/<pacote>.tar.gz
```

Use o Python do ambiente virtual e instale o empacotador como ferramenta de desenvolvimento quando necessário. O script confere igualdade com o lock, hashes/originais instalados, presença dos avisos/assets nos arquivos e padrões selecionados de arquivos privados/credenciais. É offline, não extrai arquivos nem segue links. Ele não é scanner universal de segredos ou avaliador de compatibilidade legal. Os nomes dos textos são únicos para preservar o conjunto também com empacotadores que achatem caminhos.
