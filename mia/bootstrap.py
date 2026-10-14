"""Authorize first-owner creation in native installations on shared hosts."""
from __future__ import annotations

import hmac
import os
from pathlib import Path
import re
import stat

from fastapi import HTTPException, Request

COOKIE_NAME = "mia_bootstrap"


def required() -> bool:
    return os.environ.get("MIA_SETUP_REQUIRE_TOKEN", "false").lower() == "true"


def require_owner_creation(request: Request) -> None:
    if not required():
        return
    root = os.environ.get("MIA_OPERATIONS_ROOT")
    if not root:
        raise HTTPException(503, "Esta instalação precisa de recuperação pelo aplicativo Mia.")
    path = Path(root) / "bootstrap-token"
    try:
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as incoming:
            metadata = os.fstat(incoming.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077 or metadata.st_size > 256:
                raise ValueError
            expected = incoming.read(257).decode("ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", expected):
            raise ValueError
    except (OSError, ValueError, UnicodeError):
        raise HTTPException(503, "O acesso inicial precisa de recuperação pelo aplicativo Mia.") from None
    supplied = request.cookies.get(COOKIE_NAME, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", supplied) or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "Abra esta instalação pelo aplicativo Mia para criar seu acesso.")
