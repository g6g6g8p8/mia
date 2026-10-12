"""Owner-owned preferences and reviewable access plans; never applies networking."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .db import data_dir


def https_origin(value: str) -> str:
    """Accept only an HTTPS origin whose host is safe as a Caddy site token."""
    value = value.strip().rstrip('/')
    if not value:
        return ''
    try:
        url = urlsplit(value)
        port = url.port
        host = url.hostname
    except ValueError as exc:
        raise ValueError('Endereço ou porta inválida') from exc
    if (url.scheme != 'https' or not host or url.username or url.password
            or url.path or url.query or url.fragment or port == 0
            or any(c.isspace() for c in value) or '\\' in value or '%' in host):
        raise ValueError('Informe apenas um endereço HTTPS, sem caminho, senha ou parâmetros')
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # A narrow DNS grammar also prevents configuration-directive injection.
        if (len(host) > 253 or not all(re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', label)
                                      for label in host.split('.'))):
            raise ValueError('Use um nome DNS válido ou endereço IP da máquina')
        host = host.lower()
    else:
        if ip.is_unspecified or ip.is_multicast:
            raise ValueError('O endereço de acesso precisa identificar uma máquina')
        host = f'[{ip.compressed}]' if ip.version == 6 else str(ip)
    return 'https://' + host + (f':{port}' if port is not None else '')


class AccessSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['computer', 'lan', 'remote'] = 'computer'
    address: str = Field(default='', max_length=2048)

    @model_validator(mode='after')
    def validate_address(self):
        self.address = https_origin(self.address)
        return self


class AccessPlanInput(AccessSettings):
    """Structured choices only. No paths, shell commands, or network credentials."""
    certificate: Literal['internal', 'public'] = 'internal'
    listen_address: str = Field(default='127.0.0.1', max_length=45)
    upstream_port: int = Field(default=8123, ge=1, le=65535, strict=True)
    recovery_port: int = Field(default=8443, ge=1024, le=65535, strict=True)

    @model_validator(mode='after')
    def validate_plan(self):
        try:
            if '%' in self.listen_address:
                raise ValueError('Interfaces com escopo não são aceitas neste plano')
            listener = ipaddress.ip_address(self.listen_address)
        except ValueError as exc:
            raise ValueError('Informe somente o IP da interface onde o proxy escutará') from exc
        if listener.is_multicast:
            raise ValueError('A interface do proxy não pode ser multicast')
        self.listen_address = listener.compressed
        if self.mode != 'computer':
            if not self.address:
                raise ValueError('Informe o endereço HTTPS para preparar o plano')
            url = urlsplit(self.address)
            if (url.port or 443) in {self.upstream_port, self.recovery_port}:
                raise ValueError('Use portas diferentes para HTTPS, aplicação e recuperação')
            if self.upstream_port == self.recovery_port:
                raise ValueError('Use portas diferentes para aplicação e recuperação')
            if self.certificate == 'public':
                try:
                    ipaddress.ip_address(url.hostname)
                    is_ip = True
                except ValueError:
                    is_ip = False
                if is_ip or '.' not in url.hostname or url.hostname.endswith(('.localhost', '.test', '.invalid', '.local')):
                    raise ValueError('Certificado público automático exige um domínio público sob seu controle')
        return self


def prepare(payload: AccessPlanInput) -> dict:
    """Pure plan generation: no writes, DNS queries, URL probes or processes."""
    plan = {
        'format': 'mia-access-plan', 'format_version': 1,
        'mode': payload.mode, 'address': payload.address,
        'status': {'plan': 'prepared', 'infrastructure': 'not_checked', 'access': 'not_proven'},
        'changes': [], 'files': {}, 'commands': [],
        'warnings': ['Gerar ou salvar este plano não altera a rede nem comprova acesso.',
                     'Caddy é um proxy opcional; outro proxy HTTPS pode usar os mesmos requisitos.',
                     'Este artefato supõe instalação nativa e proxy no mesmo host. Em contêiner, revisar a rede e confiar somente o IP real do proxy; nunca usar * como confiança.'],
        'checks': ['Teste login e uma alteração autenticada no dispositivo de destino.',
                   'Para acesso remoto, repita fora do Wi-Fi da instalação; uma resposta local não prova acesso externo.'],
        'recovery': ['Mantenha acesso ao terminal da máquina e um backup verificado antes de aplicar mudanças.'],
    }
    if payload.mode == 'computer':
        plan['warnings'].append('A preferência local não desativa rotas, proxies ou túneis já existentes.')
        plan['recovery'].append('Use a instalação local existente. Não mude cookie/portas para aplicar este plano.')
        return plan

    tls = 'tls internal' if payload.certificate == 'internal' else 'tls {\n        issuer acme {\n            disable_http_challenge\n        }\n    }'
    upstream = f'127.0.0.1:{payload.upstream_port}'
    caddyfile = (
        '# Plano a revisar; executar Caddy abre somente os listeners descritos abaixo.\n'
        '{\n    admin off\n    auto_https disable_redirects\n    skip_install_trust\n}\n\n'
        f'{payload.address} {{\n    bind {payload.listen_address}\n    {tls}\n'
        f'    reverse_proxy {upstream}\n}}\n\n'
        f'https://localhost:{payload.recovery_port} {{\n    bind 127.0.0.1\n    tls internal\n'
        f'    reverse_proxy {upstream}\n}}\n'
    )
    backend = ['python', '-m', 'uvicorn', 'mia.app:app', '--host', '127.0.0.1', '--port',
               str(payload.upstream_port), '--proxy-headers', '--forwarded-allow-ips', '127.0.0.1']
    plan['files'] = {'Caddyfile': caddyfile, 'mia-access.env': 'MIA_COOKIE_SECURE=true\n'}
    plan['commands'] = [
        {'purpose': 'Validar configuração sem iniciar listeners', 'argv': ['caddy', 'validate', '--config', 'Caddyfile', '--adapter', 'caddyfile']},
        {'purpose': 'Reiniciar aplicação local com cookie HTTPS; preservar MIA_DATA_DIR e demais configurações existentes',
         'argv': backend, 'environment_additions': {'MIA_COOKIE_SECURE': 'true'}},
        {'purpose': 'Aplicar somente após autorização local específica; manter este terminal aberto',
         'argv': ['caddy', 'run', '--config', 'Caddyfile', '--adapter', 'caddyfile']},
    ]
    plan['changes'] = [
        f'Proxy HTTPS em {payload.listen_address}, porta {urlsplit(payload.address).port or 443}, para {payload.address}.',
        f'Aplicação HTTP permanece em {upstream}; confiar cabeçalhos de proxy somente de 127.0.0.1.',
        'Adicionar MIA_COOKIE_SECURE=true à configuração existente e reiniciar; não substituir arquivo de ambiente completo.',
        f'Recuperação HTTPS em https://localhost:{payload.recovery_port}, ligada somente a 127.0.0.1.',
        'Caddy guarda certificados e chave da CA local em seu diretório de dados; não incluí-los no repositório.',
    ]
    if ipaddress.ip_address(payload.listen_address).is_loopback:
        plan['warnings'].append('O listener escolhido é loopback: este plano ainda não atenderá outros dispositivos.')
    elif ipaddress.ip_address(payload.listen_address).is_unspecified:
        plan['warnings'].append('O listener escolhido atende todas as interfaces; revisar alcance e firewall antes de executar.')
    if payload.certificate == 'internal':
        plan['warnings'].append('CA privada: instale sua raiz nos dispositivos somente após verificar a origem. Não ignore avisos TLS.')
    else:
        plan['changes'].append('Solicitar certificado público por ACME/TLS-ALPN; envolve rede e validação do domínio na porta 443.')
        plan['warnings'].append('Domínio, DNS e rota de entrada ainda precisam existir. CGNAT exige outra rota, servidor ou túnel opcional.')
    plan['checks'].extend([
        'Validar o Caddyfile, manter TLS verificado e conferir que a porta HTTP da aplicação continua em loopback.',
        'Na recuperação HTTPS local, confiar a CA local verificada e testar login antes de abandonar o terminal.',
        'Conferir cookie Secure/HttpOnly/SameSite e rejeição de alterações com Origin de outro site.',
    ])
    plan['recovery'].extend([
        f'No navegador da máquina, usar https://localhost:{payload.recovery_port} com a CA local confiável.',
        'Em falha, parar este proxy (Ctrl+C no terminal do plano) e restaurar a configuração anterior; isso não remove outras rotas existentes.',
        'Se a recuperação HTTPS falhar, pelo terminal pare o proxy e a Mia, restaure MIA_COOKIE_SECURE=false e reinicie a Mia apenas em 127.0.0.1. Entre novamente por HTTP local.',
        'Desligar acesso externo também exige remover qualquer encaminhamento, DNS ou túnel configurado separadamente.',
    ])
    return plan


def main() -> None:
    """Generate artifacts locally; deliberately has no apply/probe command."""
    parser = argparse.ArgumentParser(description='Preparar plano de acesso Mia sem aplicar mudanças')
    parser.add_argument('--mode', choices=['computer', 'lan', 'remote'], required=True)
    parser.add_argument('--address', default='')
    parser.add_argument('--certificate', choices=['internal', 'public'], default='internal')
    parser.add_argument('--listen-address', default='127.0.0.1')
    parser.add_argument('--upstream-port', type=int, default=8123)
    parser.add_argument('--recovery-port', type=int, default=8443)
    parser.add_argument('--output-dir', type=Path, help='Diretório novo; nunca sobrescreve um existente')
    args = parser.parse_args()
    try:
        plan = prepare(AccessPlanInput.model_validate({name: value for name, value in vars(args).items() if name != 'output_dir'}))
        if args.output_dir:
            args.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
            files = {**plan['files'], 'plan.json': json.dumps(plan, ensure_ascii=False, indent=2) + '\n'}
            for name, content in files.items():
                fd = os.open(args.output_dir / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w') as file:
                    file.write(content)
        else:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


def load() -> dict:
    path = data_dir() / 'access-settings.json'
    return AccessSettings.model_validate_json(path.read_text()).model_dump() if path.exists() else AccessSettings().model_dump()


def save(payload: AccessSettings) -> None:
    fd, temporary = tempfile.mkstemp(prefix='access-', dir=data_dir())
    try:
        with os.fdopen(fd, 'w') as file:
            json.dump(payload.model_dump(), file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, data_dir() / 'access-settings.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == '__main__':
    main()
