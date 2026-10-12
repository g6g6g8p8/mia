"""Owner-owned access preferences; never changes host networking."""
import json
import os
import tempfile
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .db import data_dir


class AccessSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['computer', 'lan', 'remote'] = 'computer'
    address: str = Field(default='', max_length=2048)

    @model_validator(mode='after')
    def validate_address(self):
        self.address = self.address.strip().rstrip('/')
        if self.address:
            url = urlsplit(self.address)
            try:
                port = url.port
            except ValueError:
                raise ValueError('Porta inválida')
            if (url.scheme != 'https' or not url.hostname or url.username or url.password
                    or url.path or url.query or url.fragment or port == 0
                    or any(c.isspace() for c in self.address) or '\\' in self.address):
                raise ValueError('Informe apenas um endereço HTTPS, sem caminho, senha ou parâmetros')
        return self


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
