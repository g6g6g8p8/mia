# Instalação nativa — macOS e Linux

Alternativa sem Docker para pilotos; Python 3.12 ou superior. Validada em macOS ARM64 com Python 3.12.13. Windows ainda não validado.

Em um clone novo do repositório:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps .
cp .env.example .env
.venv/bin/uvicorn mia.app:app --env-file .env --host 127.0.0.1 --port 8123
```

Abra `http://127.0.0.1:8123`. O diretório `data/` recebe os dados locais e nunca deve ser enviado ao Git. Para outro local, defina `MIA_DATA_DIR` no `.env`. O processo precisa ficar em execução. Esse modo manual continua suportado.

Na 0.2.0a11, a alternativa de [operação nativa gerenciada](OPERATIONS.md) prepara versões separadas, inicializa um único worker, guarda snapshot antes de atualizar e recupera em diretório novo. A atualização é uma ação explícita no terminal, com origem/versão escolhidas; não é atualização automática. Templates systemd/launchd são opcionais, exigem revisão e ativação local e não foram ativados durante o ensaio cloud. Não aponte o instalador para dados de uma instalação existente: ele exige destino novo e vazio.

O teste no Mac usou um ambiente virtual isolado, banco novo e instalação das dependências fixadas. Não reutilizou o banco, a conta ou o serviço de outra máquina. Isso valida portabilidade técnica, não a facilidade da instalação por uma pessoa sem ajuda.

Para testes de desenvolvimento, instale `.[dev]` e execute `pytest`. Os scripts `scripts/browser_smoke.py` e `scripts/browser_harness.py` exigem Playwright e seu Chromium. O primeiro exige uma instância vazia descartável; o segundo cria seu próprio banco temporário e um provedor simulado local. Nunca execute o smoke de onboarding em uma instalação com dados reais.

Sem URL, `scripts/browser_smoke.py` agora cria sua própria instalação temporária. Uma URL explícita mantém o modo antigo e deve apontar somente para uma instalação descartável. Para usar Chromium já instalado, defina `MIA_BROWSER_EXECUTABLE=/caminho/do/chromium`; sem isso, Playwright usa seu navegador empacotado. Os scripts `browser_onboarding.py`, `browser_harness.py` e `browser_operations.py` criam fixtures temporárias. Os provedores desses ensaios são simulados, sem chamadas pagas.
