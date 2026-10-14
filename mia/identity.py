"""Opaque installation identity; exposes no owner, paths or credentials."""
from __future__ import annotations

import os
from pathlib import Path
import uuid

from .db import data_dir
from .operations import _lock, _read, _write
from . import bootstrap


def installation_id() -> str:
    """Managed identity outlives data swaps; manual instances use private state.

    Session stores must also identify their connection/origin. A restored copy
    is not authorized just because its source identity matches an old backup.
    """
    managed = os.environ.get("MIA_OPERATIONS_ROOT")
    if managed:
        configuration = Path(managed) / "installation.json"
        if not configuration.is_symlink() and configuration.is_file():
            value = _read(configuration).get("installation_id")
            if value:
                return str(uuid.UUID(value))
    directory = data_dir()
    path = directory / "installation-identity.json"
    if path.is_symlink() or (directory / "installation-identity.lock").is_symlink():
        raise ValueError("Identidade da instalação não pode seguir links")
    with _lock(directory / "installation-identity.lock", blocking=True):
        if path.exists():
            return str(uuid.UUID(_read(path)["installation_id"]))
        identity = str(uuid.uuid4())
        _write(path, {"format": 1, "installation_id": identity})
        return identity


def public_info() -> dict:
    secure = os.environ.get("MIA_COOKIE_SECURE", "false").lower() == "true"
    return {"installation_id": installation_id(), "desktop_protocol": 1, "bootstrap_protected": bootstrap.required(),
            "cookie_secure": secure,
            "transport_policy": "https_required" if secure else "private_connection_only"}
