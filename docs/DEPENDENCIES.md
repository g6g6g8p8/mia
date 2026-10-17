# Dependências e escopo da revisão

Revisão técnica iniciada em 12/10/2026: 21 distribuições Python fixadas em `requirements.lock`, metadados e 24 arquivos de licença fornecidos pelos wheels instalados no Linux x86_64. Foram preservados também cinco avisos do libuv fornecido no sdist de uvloop 0.23.0 e o texto completo da MPL-2.0 para certifi: **30 textos**. O suplemento Rust acrescenta **249 textos de 140 pares crate/versão**, totalizando **279 textos**, sem reescrever atribuições. Os inventários legíveis por máquina e os SHA256 estão em `THIRD_PARTY_LICENSES/inventory.json` e `rust-inventory.json`; a tabela Python está em [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

O sdist de uvloop foi obtido do endereço de artefato publicado no índice PyPI, com HTTPS verificado e SHA256 comparado ao publicado pelo índice (`28d160f51ab4da3b187063652e643dea6831072add4adc1e6d62afbe73b6be27`). O libuv tem MIT, trechos BSD-2-Clause e ISC; os comentários iniciais de atribuição/licença de `tree.h` e `inet.c` foram copiados, sem importar código. A licença de documentação upstream (CC-BY-4.0) foi preservada por completude do conjunto, sem distribuir a documentação do libuv. O endereço oficial da Mozilla foi bloqueado pelo proxy (403); o texto MPL completo veio do arquivo de licenças da imagem Debian, com origem e hash registrados. O aviso fornecido por certifi foi mantido integralmente.

## O que está incluído

- Runtime direto: FastAPI, HTTPX e Uvicorn com extras `standard`.
- Dependências transitivas Python do lock, incluindo validação, transporte HTTP, certificados, YAML, tipagem e extras nativos do Uvicorn.
- Avisos vendorizados publicados por httptools (`http-parser` e `llhttp`) e libuv do uvloop, inclusive textos MIT/Apache-2.0 oferecidos upstream.
- Fechamento de fontes de registro nos `Cargo.lock` dos sdists verificados de `pydantic-core` 2.50.0 (99 entradas) e `watchfiles` 1.3.0 (46 entradas): 140 pares distintos após remover sobreposição. Os arquivos incluem dependências de build/desenvolvimento e plataformas opcionais; isso não afirma que todas entram em cada wheel.
- Preservação dos textos no repositório, wheel e sdist; Docker copia o mesmo conjunto antes de instalar a Mia. O wheel da Mia declara dependências, não embute seus binários.

## Componentes da distribuição Mac a13

O aplicativo SwiftUI/AppKit + WKWebView usa o framework Sparkle **2.10.0**, fixado em `macos/Mia/Package.swift` e `Package.resolved` no commit upstream `eef1a539a373c1f1a320624b1130fc5de7b2e100`. `THIRD_PARTY_LICENSES/native-inventory.json` registra a revisão, endereço e SHA256 do arquivo Swift Package Manager e do texto original `native-sparkle-2.10.0--LICENSE`. Esse texto conserva a licença MIT do Sparkle e os avisos BSD/Ed25519 nele fornecidos, sem resumi-los. O empacotador copia o framework para o `.app` e inclui o inventário/aviso; a checagem de distribuição recusa divergência entre versão/revisão declaradas e avisos preservados.

Os runtimes incluídos são CPython **3.12.15**, da publicação **20261013** de `astral-sh/python-build-standalone`, específicos para Mac arm64, Mac x86_64 e o companion Linux x86_64. `scripts/macos-runtime-lock.json` fixa os arquivos, SHA256, revisão upstream e índice de checksums. `scripts/prepare_macos_artifacts.py` conserva proveniência, confere o inventário de arquivos e verifica os bytes novamente contra os arquivos upstream autenticados. Os 24 wheels de runtime/bootstrap são conferidos contra hashes publicados no PyPI e registrados por plataforma; um conjunto Linux não substitui os wheels Mac.

A preparação lê `PYTHON.json` e os textos de licença do arquivo completo upstream, além do runtime `install_only`; incorpora os avisos desses componentes no artefato. A publicação upstream referencia um aviso zlib-ng ausente do arquivo completo. O lock registra um suplemento obtido do pacote-fonte exato zlib-ng 2.2.4, com SHA256 do pacote e do texto, em vez de ignorar o aviso faltante. A contagem/inventário do runtime exato fica com cada artefato, separado das 279 cópias Python/Rust do inventário histórico.

O companion Linux omite somente o prefixo opcional `python/share/terminfo` antes da extração: aliases de terminais com nomes distintos apenas por caixa colidem no APFS padrão. A transformação registra o índice/hash e contagens dos membros omitidos e permanece verificável contra o arquivo upstream. Bytes do Python, bibliotecas e avisos retidos permanecem iguais; essa normalização não desativa TLS, hashes ou verificações de links/caminhos. O companion não é executado em Mac para fingir validação Linux.

Compilação/testes Swift passaram em runners macOS 15 arm64 e Intel, e o runtime Linux foi ensaiado offline com contexto sintético. Assinatura altera bytes de executáveis; o script conserva a proveniência upstream e registra o novo inventário após assinar. A produção ainda exige identidade Developer ID, notarização e aceites dos artefatos finais. Isso não é uma auditoria jurídica completa dos binários, do SDK Apple ou do sistema operacional.

MIT/BSD requerem preservar os avisos e textos aplicáveis. Apache inclui condições de atribuição, arquivos modificados e `NOTICE` quando fornecido. PSF conserva seu acordo e histórico. MPL aplica obrigações aos arquivos cobertos, sem automaticamente relicenciar os arquivos próprios e separados da Mia; se certifi for modificado ou redistribuído em uma imagem, cumprir acesso à fonte correspondente e avisos. A tabela reproduz identificadores declarados ou confirmados nos textos; não concede licença à Mia.

## Fontes nativas/Rust

Os dois sdists Python foram obtidos do índice PyPI e seus SHA256 publicados foram conferidos. Para cada entrada de registro no `Cargo.lock`, o arquivo `.crate` foi obtido de `static.crates.io` por HTTPS verificado e conferido contra o checksum do lock antes da leitura. Foram copiados somente arquivos upstream de licença/NOTICE/COPYING e metadados públicos de atribuição, sem importar implementação. `rust-inventory.json` registra endereço, SHA256 do pacote-fonte, membro original e SHA256 de cada cópia; também registra origem/hash dos sdists e dos locks usados.

A inspeção encontrou dois casos sem arquivos chamados LICENSE: `r-efi` contém o texto de licença e copyright em `AUTHORS`, preservado integralmente; `wit-bindgen-rt` usa licenças no repositório upstream, obtidas pelo commit exato informado em `.cargo_vcs_info.json` do crate verificado, com HTTPS e hash de cada texto. Esses caminhos são selecionados por `getrandom` para UEFI/backend EFI e wasm32/WASI p2, respectivamente, conforme seus manifests, e não são os caminhos Linux/macOS. Suas alternativas declaradas foram preservadas mesmo assim. Uma expressão `OR` oferece alternativas; não implica escolher simultaneamente todas, nem obriga aplicar uma delas à Mia.

Além de MIT/Apache/BSD, o suplemento conserva avisos Unicode-3.0/Unicode-DFS-2016, ISC, Zlib, CC0, Unlicense e a exceção LLVM quando fornecida. Há licença de terceiros dentro de arquivos como `crossbeam-channel/LICENSE-THIRD-PARTY` e tabelas Unicode de regex; eles também são preservados. Não tratar um arquivo de licença principal como prova de ausência de avisos adicionais.

## Limites e próximos passos

Este inventário **não é uma liberação jurídica de todos os artefatos**. O suplemento enumera a árvore de fontes de registro dos locks, mas não reproduz o build de cada wheel upstream nem comprova quais componentes foram incorporados em um binário específico. A inspeção de nomes de arquivos e metadados não é uma auditoria de todos os comentários de licença por arquivo. O inventário original de wheels não cobria o runtime Python; a revisão a13 acima acrescenta a proveniência/avisos do runtime incluído e Sparkle. Imagem base, SDK Apple e sistema operacional completo ficam fora do escopo. Dependências de desenvolvimento Python (`pytest`, seus plugins, empacotador) também têm avisos próprios e não fazem parte do runtime publicado pela Mia.

Para distribuir imagens/binários que incluam essas bibliotecas, gerar inventário do artefato exato com plataforma/digests e conferir obrigações de avisos/fontes dos componentes incorporados, inclusive sistema operacional, antes de publicação ampla. As dependências não são código extraído de um projeto pessoal; nenhum histórico ou dado privado do usuário foi copiado para esta revisão. Atribuições/emails públicos dos autores de dependências nos avisos originais são conservados. A licença própria Apache-2.0 e NOTICE foram aplicados por escolha delegada do proprietário; [escopo](LICENSE-OPTIONS.md). Isso não altera licenças de terceiros nem certifica todos os binários do sistema.

Uma troca de versão, extras, plataforma ou imagem exige nova revisão dos artefatos correspondentes. Não atualizar o JSON apenas para passar a checagem; obter os textos da nova versão, preservar atribuições e registrar sua origem/hash. Em plataformas que omitam extras nativos, conferir o subconjunto instalado sem declarar o ensaio Linux como evidência de instalação no Mac.

## Conferência reproduzível

```bash
python scripts/check_distribution.py --installed
python -m build --outdir /tmp/mia-dist
python scripts/check_distribution.py --archive /tmp/mia-dist/<pacote>.whl --archive /tmp/mia-dist/<pacote>.tar.gz
```

Use o Python do ambiente virtual e instale o empacotador como ferramenta de desenvolvimento quando necessário. O script confere igualdade com o lock, origem/versões/contagens do suplemento Rust, hashes/originais Python instalados, inventário/licença e fixação de fonte do Sparkle, ausência de arquivos não registrados no diretório de licenças, presença de todos os avisos/assets nos arquivos e padrões selecionados de arquivos privados/credenciais. É offline, não extrai arquivos nem segue links. Ele não é scanner universal de segredos ou avaliador de compatibilidade legal. Os nomes dos textos são únicos para preservar o conjunto também com empacotadores que achatem caminhos. O runtime Mac/companion tem verificação própria em `scripts/prepare_macos_artifacts.py`, executada pelo build descrito em [MAC-DEMO-IMPLEMENTATION.md](MAC-DEMO-IMPLEMENTATION.md).

Validação técnica da distribuição `0.2.0a11`: Linux x86_64, Python 3.12.14; 13 testes de comportamento do verificador passaram. Wheel e sdist novos passaram com setuptools 84.0.0 (`build` 1.6.1, `wheel` 0.48.0) e com setuptools 75.0.0, o mínimo declarado pelo projeto. As 279 licenças, os dois inventários e o aviso geral foram preservados byte a byte: 282 arquivos. Um ambiente virtual novo recebeu o lock e o wheel; a conferência dos avisos de runtime/metadados instalados e `scripts/package_smoke.py` passaram, com inicialização HTTP/assets fora do diretório-fonte. Isso é validação no host Linux existente, não instalação de sistema operacional novo, revisão de imagem completa, teste Mac ou concessão da licença própria.

## Build Docker com wheelhouse verificado

`scripts/build_offline_image.py` prepara um contexto temporário explícito com arquivos públicos de empacotamento, código/assets da Mia e avisos; não copia o checkout inteiro, Git, arquivos de ambiente, dados ou backups. Seleciona somente wheels das versões do lock e do bootstrap (`pip` 25.0.1, setuptools 75.8.0, `wheel` 0.45.1), verifica os SHA256 publicados pelo PyPI com HTTPS normal no host e gera locks com `--require-hashes`. No Dockerfile temporário, substitui o bloco de instalação por `--no-index --find-links` e instala a Mia com `--no-build-isolation`; executa o build com `--network none`. O Dockerfile original permanece igual. A imagem base precisa estar disponível no cache ou ser obtida pelo Docker com sua configuração normal de confiança; `--network none` não impede sozinho essa obtenção.

```bash
python scripts/build_offline_image.py \
  --wheelhouse /caminho/wheels-verificados \
  --tag mia:0.2.0a11-review \
  --write-hash-manifest /tmp/mia-wheel-hashes.json \
  --manifest-output /tmp/mia-image-source.json \
  --validate
```

Os manifests públicos ficam fora do checkout e não são sobrescritos. Em uma repetição sem acesso ao índice no host, use `--hash-manifest /tmp/mia-wheel-hashes.json` no lugar de `--write-hash-manifest`, com o manifest previamente verificado e conservado sob controle do instalador; compare os hashes antes de qualquer instalação. É necessário fornecer wheels compatíveis com o Python/plataforma da imagem; não interpretar um conjunto Linux x86_64 como pacote para toda arquitetura. `DOCKER_CONFIG`, quando necessário no cloud, aponta para uma configuração existente fora do checkout; o helper não copia credenciais ou configurações privadas para o contexto.

Ensaio efetivo: imagem local `mia:0.2.0a11-review`, Linux/amd64, ID `sha256:9d483221701a4d7863dba88ff8dbfe3170164d005358ebbfae793490e38c6cc1`. Build com rede dos comandos RUN desativada, 24 wheels conferidos e instalação sem dependências quebradas. Com rede dos contêineres desativada e usuário 10001, passaram HTTP/assets fora de `/app`, comparação dos 282 avisos/inventários do pacote instalado e instalação vazia → autenticação → tarefa sintética → reinício → uma única tarefa preservada. Checkers e avisos foram montados somente leitura a partir de cópias públicas temporárias; os contêineres/dados sintéticos foram removidos. Guardas adicionais rejeitaram uma roda alterada e fonte dentro de diretório privado em reproduções sintéticas.

O primeiro ensaio encontrou permissão insuficiente nos scripts originais montados, que tinham modo 0600. O helper passou a usar cópias públicas temporárias 0644/diretórios 0755, mantendo o UID 10001 e todas as permissões do checkout. O build convencional teve falha de DNS no ambiente cloud; o build offline acima não comprova sucesso daquela rota de rede, instalação de VM completa, HTTPS remoto ou auditoria legal de todos os componentes da imagem. Nenhuma verificação TLS/assinatura foi desabilitada para contornar essas falhas.
