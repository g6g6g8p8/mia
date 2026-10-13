# Dependências e escopo da revisão

Revisão técnica iniciada em 12/10/2026: 21 distribuições Python fixadas em `requirements.lock`, metadados e 24 arquivos de licença fornecidos pelos wheels instalados no Linux x86_64. Foram preservados também cinco avisos do libuv fornecido no sdist de uvloop 0.23.0 e o texto completo da MPL-2.0 para certifi: **30 textos**. O suplemento Rust acrescenta **249 textos de 140 pares crate/versão**, totalizando **279 textos**, sem reescrever atribuições. Os inventários legíveis por máquina e os SHA256 estão em `THIRD_PARTY_LICENSES/inventory.json` e `rust-inventory.json`; a tabela Python está em [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

O sdist de uvloop foi obtido do endereço de artefato publicado no índice PyPI, com HTTPS verificado e SHA256 comparado ao publicado pelo índice (`28d160f51ab4da3b187063652e643dea6831072add4adc1e6d62afbe73b6be27`). O libuv tem MIT, trechos BSD-2-Clause e ISC; os comentários iniciais de atribuição/licença de `tree.h` e `inet.c` foram copiados, sem importar código. A licença de documentação upstream (CC-BY-4.0) foi preservada por completude do conjunto, sem distribuir a documentação do libuv. O endereço oficial da Mozilla foi bloqueado pelo proxy (403); o texto MPL completo veio do arquivo de licenças da imagem Debian, com origem e hash registrados. O aviso fornecido por certifi foi mantido integralmente.

## O que está incluído

- Runtime direto: FastAPI, HTTPX e Uvicorn com extras `standard`.
- Dependências transitivas Python do lock, incluindo validação, transporte HTTP, certificados, YAML, tipagem e extras nativos do Uvicorn.
- Avisos vendorizados publicados por httptools (`http-parser` e `llhttp`) e libuv do uvloop, inclusive textos MIT/Apache-2.0 oferecidos upstream.
- Fechamento de fontes de registro nos `Cargo.lock` dos sdists verificados de `pydantic-core` 2.50.0 (99 entradas) e `watchfiles` 1.3.0 (46 entradas): 140 pares distintos após remover sobreposição. Os arquivos incluem dependências de build/desenvolvimento e plataformas opcionais; isso não afirma que todas entram em cada wheel.
- Preservação dos textos no repositório, wheel e sdist; Docker copia o mesmo conjunto antes de instalar a Mia. O wheel da Mia declara dependências, não embute seus binários.

MIT/BSD requerem preservar os avisos e textos aplicáveis. Apache inclui condições de atribuição, arquivos modificados e `NOTICE` quando fornecido. PSF conserva seu acordo e histórico. MPL aplica obrigações aos arquivos cobertos, sem automaticamente relicenciar os arquivos próprios e separados da Mia; se certifi for modificado ou redistribuído em uma imagem, cumprir acesso à fonte correspondente e avisos. A tabela reproduz identificadores declarados ou confirmados nos textos; não concede licença à Mia.

## Fontes nativas/Rust

Os dois sdists Python foram obtidos do índice PyPI e seus SHA256 publicados foram conferidos. Para cada entrada de registro no `Cargo.lock`, o arquivo `.crate` foi obtido de `static.crates.io` por HTTPS verificado e conferido contra o checksum do lock antes da leitura. Foram copiados somente arquivos upstream de licença/NOTICE/COPYING e metadados públicos de atribuição, sem importar implementação. `rust-inventory.json` registra endereço, SHA256 do pacote-fonte, membro original e SHA256 de cada cópia; também registra origem/hash dos sdists e dos locks usados.

A inspeção encontrou dois casos sem arquivos chamados LICENSE: `r-efi` contém o texto de licença e copyright em `AUTHORS`, preservado integralmente; `wit-bindgen-rt` usa licenças no repositório upstream, obtidas pelo commit exato informado em `.cargo_vcs_info.json` do crate verificado, com HTTPS e hash de cada texto. Esses caminhos são selecionados por `getrandom` para UEFI/backend EFI e wasm32/WASI p2, respectivamente, conforme seus manifests, e não são os caminhos Linux/macOS. Suas alternativas declaradas foram preservadas mesmo assim. Uma expressão `OR` oferece alternativas; não implica escolher simultaneamente todas, nem obriga aplicar uma delas à Mia.

Além de MIT/Apache/BSD, o suplemento conserva avisos Unicode-3.0/Unicode-DFS-2016, ISC, Zlib, CC0, Unlicense e a exceção LLVM quando fornecida. Há licença de terceiros dentro de arquivos como `crossbeam-channel/LICENSE-THIRD-PARTY` e tabelas Unicode de regex; eles também são preservados. Não tratar um arquivo de licença principal como prova de ausência de avisos adicionais.

## Limites e próximos passos

Este inventário **não é uma liberação jurídica de todos os artefatos**. O suplemento enumera a árvore de fontes de registro dos locks, mas não reproduz o build de cada wheel upstream nem comprova quais componentes foram incorporados em um binário específico. A inspeção de nomes de arquivos e metadados não é uma auditoria de todos os comentários de licença por arquivo. Pacotes do Python, da imagem base e do sistema operacional ficam fora do escopo. Dependências de desenvolvimento Python (`pytest`, seus plugins, empacotador) também têm avisos próprios e não fazem parte do runtime publicado pela Mia.

Para distribuir imagens/binários que incluam essas bibliotecas, gerar inventário do artefato exato com plataforma/digests e conferir obrigações de avisos/fontes dos componentes incorporados, inclusive sistema operacional, antes de publicação ampla. As dependências não são código extraído de um projeto pessoal; nenhum histórico ou dado privado do usuário foi copiado para esta revisão. Atribuições/emails públicos dos autores de dependências nos avisos originais são conservados, conforme exigência de preservação. Licença própria e revisão de titularidade continuam pendentes: [opções concretas](LICENSE-OPTIONS.md).

Uma troca de versão, extras, plataforma ou imagem exige nova revisão dos artefatos correspondentes. Não atualizar o JSON apenas para passar a checagem; obter os textos da nova versão, preservar atribuições e registrar sua origem/hash. Em plataformas que omitam extras nativos, conferir o subconjunto instalado sem declarar o ensaio Linux como evidência de instalação no Mac.

## Conferência reproduzível

```bash
python scripts/check_distribution.py --installed
python -m build --outdir /tmp/mia-dist
python scripts/check_distribution.py --archive /tmp/mia-dist/<pacote>.whl --archive /tmp/mia-dist/<pacote>.tar.gz
```

Use o Python do ambiente virtual e instale o empacotador como ferramenta de desenvolvimento quando necessário. O script confere igualdade com o lock, origem/versões/contagens do suplemento Rust, hashes/originais Python instalados, ausência de arquivos não registrados no diretório de licenças, presença de todos os avisos/assets nos arquivos e padrões selecionados de arquivos privados/credenciais. É offline, não extrai arquivos nem segue links. Ele não é scanner universal de segredos ou avaliador de compatibilidade legal. Os nomes dos textos são únicos para preservar o conjunto também com empacotadores que achatem caminhos.

Validação técnica da distribuição `0.2.0a11`: Linux x86_64, Python 3.12.14; 13 testes de comportamento do verificador passaram. Wheel e sdist novos passaram com setuptools 84.0.0 (`build` 1.6.1, `wheel` 0.48.0) e com setuptools 75.0.0, o mínimo declarado pelo projeto. As 279 licenças, os dois inventários e o aviso geral foram preservados byte a byte: 282 arquivos. Um ambiente virtual novo recebeu o lock e o wheel; a conferência dos avisos de runtime/metadados instalados e `scripts/package_smoke.py` passaram, com inicialização HTTP/assets fora do diretório-fonte. Isso é validação no host Linux existente, não instalação de sistema operacional novo, revisão de imagem completa, teste Mac ou concessão da licença própria.
