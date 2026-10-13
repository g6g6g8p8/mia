# Acesso à Mia

Em **Sistema → Acesso à Mia**, escolha computador, rede local ou acesso remoto. O assistente salva a preferência e um endereço HTTPS opcional, prepara uma prévia de mudanças e arquivos de proxy para revisão, e verifica a sessão autenticada no endereço atual. Nenhuma conta central, VPN, marca de túnel ou proxy é obrigatória.

Salvar preferência ou preparar plano não abre nem fecha portas, não instala proxy/certificados, não muda domínio e não comprova acesso externo. HTTPS da sessão e configuração de cookie são verificações distintas. Teste o endereço pelo dispositivo de destino; para remoto, teste fora do Wi-Fi da instalação. Não usar o diagnóstico da sessão atual como prova de acesso externo.

As preferências ficam em `MIA_DATA_DIR/access-settings.json` com permissão 0600, fora do repositório e do backup SQLite. São específicas da máquina: após restaurar em outra instalação, revise-as. A API exige proprietário autenticado e aplica a proteção de origem existente. Não há chamadas do servidor ao endereço informado. `POST /api/access/plan` é uma geração pura com resposta `Cache-Control: no-store`: não salva preferência nem executa comandos.

## Estado e caminhos

| Caminho | Preparação disponível | Infraestrutura e prova ainda necessárias |
| --- | --- | --- |
| Computador | Endereço local existente; plano sem alterações | Login na própria máquina; não desliga publicação prévia |
| LAN | IP de listener explícito, endereço HTTPS, CA privada ou domínio público, recuperação loopback | Rota local, resolução de nome/IP, confiança na CA e login em outro dispositivo |
| Remoto | Mesmo proxy e recuperação, opção de ACME público | Domínio sob controle, DNS, rota de entrada autorizada, certificado confiável e login fora da LAN |

O plano registra `prepared`, infraestrutura `not_checked` e acesso `not_proven`. Downloads são artefatos a revisar, não comprovação de execução. Alterar um campo remove a prévia anterior. O diagnóstico da sessão continua separado: responder em um endereço não comprova DNS, firewall ou acesso de outro local.

## Prévia revisável e aplicação local

Preencha endereço HTTPS, certificado, IP da interface do proxy e portas. O plano lista as mudanças, os arquivos `Caddyfile` e `mia-access.env`, argumentos fixos de inicialização, verificações e recuperação. A entrada aceita somente campos estruturados: nenhum caminho de arquivo, comando arbitrário ou instrução da IA é executado pelo servidor. Endereços devem ser origens HTTPS sem usuário, senha, caminho, parâmetros ou fragmento. Host DNS/IP e listener IP usam gramática restrita; portas conflitantes e campos extras são rejeitados.

O artefato opcional do Caddy supõe **instalação nativa e proxy no mesmo host**. A Mia continua em `127.0.0.1`, confiando cabeçalhos encaminhados somente por `127.0.0.1`. O proxy HTTPS escuta no IP e porta apresentados. `127.0.0.1` mantém o ensaio local; um endereço LAN deve ser selecionado para outros dispositivos. `0.0.0.0` atende todas as interfaces e exige revisão do alcance/firewall antes da aplicação. Em Docker, a conexão do proxy pode aparecer com IP da bridge: revise a topologia e confie somente o IP real do proxy; não copie as flags nativas cegamente nem use `*`.

O Caddyfile desativa o endpoint administrativo, redirecionamento HTTP e instalação automática da raiz de confiança. O certificado privado exige confiar explicitamente a CA nos dispositivos depois de verificar sua origem. O certificado público opcional usa ACME com desafio TLS-ALPN na porta pública 443; não usa desafio HTTP nem abre listener HTTP de redirecionamento. DNS e rota até essa porta continuam externos. O plano não configura conta de fornecedor. Outro proxy pode atender aos mesmos requisitos de HTTPS, Host preservado e encaminhamento confiável.

Também é possível gerar os mesmos artefatos pelo terminal. O diretório de saída deve ser novo: recebe permissão 0700 e arquivos 0600; o comando recusa sobrescrever um diretório existente.

```bash
.venv/bin/python -m mia.access --mode lan --address https://mia.home:9443 --listen-address 192.168.1.20 --output-dir /tmp/mia-access-plan
```

Isso somente prepara arquivos. Revise `plan.json` e `Caddyfile`. Instale um proxy pela distribuição oficial, com verificações de integridade/TLS preservadas. Após autorização específica das mudanças na instalação escolhida, valide o Caddyfile e aplique pelo terminal. Adicione `MIA_COOKIE_SECURE=true` ao ambiente existente, preservando diretório de dados e demais configurações; não substitua o arquivo completo pelo fragmento gerado. Reinicie a aplicação com os argumentos do plano antes de iniciar o proxy. A interface não oferece aplicação remota ou execução de shell.

## Recuperação e desligamento

Antes de aplicar, faça um backup verificado e mantenha acesso ao terminal da máquina. O plano inclui `https://localhost:8443` (porta configurável) ligado somente a `127.0.0.1`, com CA privada. Confie a raiz local verificada e teste login nessa rota. **Cookie Secure impede login por HTTP**: HTTP local não é o caminho de recuperação enquanto essa opção estiver ativa.

Se o proxy falhar, use o terminal: pare o proxy e a Mia, restaure a configuração anterior, volte `MIA_COOKIE_SECURE=false` e reinicie a aplicação somente em `127.0.0.1`. Então entre novamente pelo HTTP local. A restauração de banco continua seguindo [BACKUP.md](BACKUP.md), em diretório vazio. Não exponha a aplicação HTTP para recuperar acesso.

Para interromper o proxy do plano iniciado no terminal, use Ctrl+C; em serviço persistente, pare o serviço correspondente. Isso não desliga rotas, túneis ou proxies independentes já existentes: remova-os separadamente para revogar publicação externa. Reconfirme login local e faça o teste externo de desligamento.

## Ensaio isolado reproduzível

```bash
.venv/bin/python scripts/https_access_rehearsal.py --caddy /caminho/para/caddy
```

O script exige um executável Caddy já instalado e confiável. Escolhe portas altas livres, gera o Caddyfile pelo mesmo `prepare`, mantém todos os listeners em loopback e usa diretórios/banco temporários com identidade sintética. Verifica o certificado usando a CA do ensaio explicitamente, sem instalar confiança no sistema ou ignorar TLS. Encerra os processos e remove os temporários, inclusive em falha.

Ensaio executado no Linux em 12/10/2026 com Python 3.12 e Caddy 2.10.2. O binário foi obtido do release oficial e comparado com o SHA512 oficial. Passaram validação do Caddyfile, instalação vazia, sessão HTTPS com cookie Secure/HttpOnly/SameSite, alteração de mesma origem, rejeição de origem externa, não envio do cookie ao HTTP local, login/logout pela recuperação HTTPS e rejeição do certificado sem confiança na CA. O Caddyfile público também passou adaptação/validação; não foi iniciado e nenhum certificado público foi solicitado.

Isso valida o proxy e o fluxo HTTPS em ambiente isolado. Não valida firewall do Ubuntu/macOS, DNS público, roteador, CGNAT, CA instalada em dispositivo externo, acesso pela LAN/internet nem serviço de uma instalação real.

Limites: aplicação do plano na máquina, configuração do sistema operacional, domínio e rota de entrada ainda são externas. CGNAT pode exigir outra rota, servidor próprio ou túnel opcional. Nenhuma infraestrutura real foi publicada por este ensaio.
