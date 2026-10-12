"""Explicit metadata probe; never sends user context or requests generation."""
import json
import asyncio

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import harness


class Destination(BaseModel):
    model_config = ConfigDict(extra='forbid')
    endpoint: str = Field(max_length=2048)
    model: str = Field(max_length=200)


async def check(expected: Destination) -> dict:
    settings = harness.config(include_secret=True)
    if not settings['endpoint'] or not settings['model']:
        raise HTTPException(422, 'Salve endereço e modelo antes de verificar.')
    if (expected.endpoint, expected.model) != (settings['endpoint'], settings['model']):
        raise HTTPException(409, 'A configuração mudou. Reabra esta tela e confira o destino salvo.')
    headers = {'Accept': 'application/json'}
    if settings['_key']:
        headers['Authorization'] = 'Bearer ' + settings['_key']
    def result(status, message):
        return {'status': status, 'message': message, 'endpoint': settings['endpoint'], 'model': settings['model']}
    try:
        # Do not forward credentials through redirects or environment proxies.
        async with asyncio.timeout(10), httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
            async with client.stream('GET', settings['endpoint'] + '/models', headers=headers) as response:
                code = response.status_code
                if code in {401, 403}:
                    return result('denied', 'O serviço recusou o acesso ao catálogo. Confira a chave e as permissões no provedor.')
                if code in {404, 405, 501}:
                    return result('unsupported', 'Este endereço não oferece o catálogo esperado. Confira a URL; isso não comprova falha na geração.')
                if code != 200:
                    return result('unavailable', 'Não foi possível consultar o catálogo agora. Nenhuma geração foi solicitada; tente novamente manualmente.')
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 2 * 1024 * 1024:
                        return result('unsupported', 'O catálogo excede o limite da verificação. A compatibilidade continua não verificada.')
                payload = json.loads(body)
    except (httpx.HTTPError, ValueError, TypeError, TimeoutError):
        return result('unavailable', 'Não foi possível ler o catálogo. Confira endereço, rede e certificado. Nenhuma geração foi solicitada.')
    entries = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return result('unsupported', 'O catálogo usa um formato não reconhecido. A compatibilidade continua não verificada.')
    found = any(isinstance(item, dict) and item.get('id') == settings['model'] for item in entries)
    if found:
        return result('listed', 'Catálogo acessível e identificador do modelo encontrado. Isso não valida geração, ferramentas, saldo ou qualidade; catálogos públicos também não comprovam a chave.')
    return result('not_listed', 'Catálogo acessível, mas o identificador exato não foi encontrado. Pode ser um alias; confira no provedor. Isso não valida a chave nem a geração.')
