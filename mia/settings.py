"""Installation-owned settings, outside the repository and export."""
import json
import os
import tempfile
from decimal import Decimal
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .db import data_dir


class AISettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    endpoint: str = Field(default="", max_length=2048)
    model: str = Field(default="", max_length=200)
    api_key: str | None = Field(default=None, max_length=2048)
    daily_call_limit: int = Field(default=20, ge=1, le=1000)
    daily_budget_usd: Decimal | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    input_usd_per_million: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    output_usd_per_million: Decimal | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_destination(self):
        self.endpoint = self.endpoint.strip().rstrip("/")
        self.model = self.model.strip()
        if self.endpoint:
            p = urlsplit(self.endpoint)
            local = p.hostname in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
            if not p.hostname or p.username or p.password or p.query or p.fragment or not (p.scheme == "https" or p.scheme == "http" and local):
                raise ValueError("Use HTTPS; HTTP só para o motor local")
        if self.enabled and not (self.endpoint and self.model):
            raise ValueError("Informe endereço e modelo antes de ativar")
        if self.daily_budget_usd is not None and (self.input_usd_per_million is None or self.output_usd_per_million is None):
            raise ValueError("Um orçamento exige os dois preços por milhão de tokens")
        return self


def load() -> dict:
    path = data_dir() / "ai-settings.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save(payload: AISettings) -> None:
    prior = load()
    values = payload.model_dump(mode="json")
    if payload.api_key is None:
        # Never carry a secret to a newly selected destination.
        values["api_key"] = prior.get("api_key", "") if prior.get("endpoint") == payload.endpoint else ""
    p = urlsplit(payload.endpoint)
    local = p.hostname in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
    if payload.enabled and not local and not values["api_key"]:
        raise HTTPException(422, "Informe uma chave para este destino")
    fd, temporary = tempfile.mkstemp(prefix="settings-", dir=data_dir())
    try:
        with os.fdopen(fd, "w") as file:
            json.dump(values, file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, data_dir() / "ai-settings.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def key() -> str:
    values = load()
    return values.get("api_key", "") if values else os.environ.get("MIA_AI_API_KEY", "")
