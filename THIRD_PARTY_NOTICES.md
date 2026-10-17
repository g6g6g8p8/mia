# Third-party notices / Avisos de terceiros

These notices apply to third-party components, not to Mia's own code.
No license for Mia is granted by this file. Keep the original license and
copyright texts with any redistribution of the covered components.

Revisão técnica: 12/10/2026, Linux x86_64. Este conjunto conserva os avisos de
21 distribuições Python fixadas em `requirements.lock`, incluindo textos
vendorizados fornecidos por httptools/uvloop, e a MPL-2.0 completa: 30 textos.
O suplemento registra 140 pares crate/versão dos Cargo.lock de pydantic-core
2.50.0 e watchfiles 1.3.0, conservando mais 249 textos, totalizando 279.
Eles não foram modificados. Os dois comentários de licença de libuv foram
extraídos literalmente com nova linha final, sem importar o código restante.

Os textos e atribuições originais estão em `THIRD_PARTY_LICENSES/`; os nomes
únicos identificam pacote/versão/componente. `inventory.json` registra origem,
SHA256 de cada cópia e SHA256 do sdist upstream quando utilizado.
`rust-inventory.json` registra licenças declaradas, pacotes-fonte/checksums
conferidos contra os Cargo.lock e seus membros originais. Esse fechamento
inclui build/desenvolvimento e plataformas opcionais; não afirma que todos os
crates estejam compilados em cada wheel. Os mesmos
textos acompanham wheel/sdist e são copiados na construção da imagem.

O cliente Mac adiciona Sparkle 2.10.0, fixado no Swift Package Manager. Seu
LICENSE original completo, incluindo avisos de componentes BSD/MIT e Ed25519,
está preservado em `native-sparkle-2.10.0--LICENSE`; `native-inventory.json`
registra versão, origem e hashes do aviso/artefato upstream. Esses avisos não
alteram as licenças próprias dos componentes nem concedem uma licença da Mia.
O runtime Python standalone tem fechamento de avisos próprio, extraído da
distribuição oficial completa e incluído pelo pipeline no artefato Mac.

| Componente | Versão revisada | Licença declarada ou confirmada no texto |
| --- | --- | --- |
| annotated-types | 0.8.0 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| anyio | 4.15.1 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| fastapi | 0.115.6 | MIT |
| h11 | 0.16.0 | MIT |
| httptools | 0.9.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| pydantic | 2.14.0 | MIT |
| pydantic-core | 2.50.0 | MIT |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT |
| starlette | 0.41.3 | BSD-3-Clause |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| uvicorn | 0.34.0 | BSD-3-Clause |
| uvloop | 0.23.0 | MIT OR Apache-2.0; libuv: MIT/BSD-2-Clause/ISC |
| watchfiles | 1.3.0 | MIT |
| websockets | 17.2 | BSD-3-Clause |
| Sparkle (cliente Mac) | 2.10.0 | MIT e avisos dos componentes incluídos |

As licenças MIT, BSD, Apache, PSF e MPL têm obrigações próprias de preservação
ou distribuição; leia os textos originais. O libuv oferece avisos adicionais
MIT/BSD-2-Clause/ISC; `LICENSE-docs` upstream (CC-BY-4.0) é preservado, embora a
documentação do libuv não seja distribuída pela Mia. O conteúdo de certifi é
coberto pelo aviso MPL fornecido pelo pacote; a licença completa acompanha o
aviso e a fonte upstream está identificada nos metadados originais/PyPI.

Scope limits: this is an inventory of pinned Python distributions and available
bundled notices, plus the registry source closure in the reviewed Rust locks.
It is not a reconstruction of every upstream native wheel build or a complete
audit of per-file notices, Python/the operating system/base-image packages,
development tools, trademark rights or project ownership. A distributor of an
image or native dependency bundle must review those exact artifacts and source/notice
requirements before a broad release. Do not infer license compatibility or a
project license from this table. Details: `docs/DEPENDENCIES.md` and
`docs/LICENSE-OPTIONS.md`. Changes to versions, extras, platforms or image
digests require a new review and updated original notices.
