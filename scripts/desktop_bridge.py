#!/usr/bin/env python3
"""One bounded JSON request/response for the native app; no shell or web bridge."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


MAX_REQUEST = 64 * 1024
MAX_RESPONSE = 2 * 1024 * 1024


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def main() -> None:
    # In a packaged app this file is Resources/desktop_bridge.py. A source
    # checkout supports diagnostics/tests only; requests cannot choose either.
    location = Path(__file__).resolve().parent
    resources = location if (location / "source/mia").is_dir() else location.parent
    source = resources / "source" if (resources / "source/mia").is_dir() else resources
    sys.path.insert(0, str(source))
    response = {"ok": False, "error": {"code": "invalid_request", "message": "A solicitação do aplicativo é inválida."}}
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if not raw or len(raw) > MAX_REQUEST:
            raise ValueError("bounded request")
        request = json.loads(raw, object_pairs_hook=_object)
        if not isinstance(request, dict) or set(request) != {"action", "payload"} or not isinstance(request["action"], str) or len(request["action"]) > 64 or not isinstance(request["payload"], dict):
            raise ValueError("request shape")
        from mia.desktop import DesktopController
        # Manager and third-party code cannot contaminate stdout's protocol.
        with redirect_stdout(io.StringIO()):
            result = DesktopController(resources).handle(request["action"], request["payload"])
        response = {"ok": True, "result": result}
    except (ValueError, UnicodeError, RecursionError):
        pass
    except Exception as error:
        # Only explicit safe operation errors can supply user-facing messages.
        code = getattr(error, "code", None)
        try:
            from mia.operations import OperationError
            safe = isinstance(error, OperationError) and isinstance(code, str) and hasattr(error, "message")
        except ImportError:
            safe = False
        if safe:
            response = {"ok": False, "error": {"code": code, "message": error.message}}
        else:
            response = {"ok": False, "error": {"code": "operation_failed", "message": "A Mia não concluiu a operação. Seus dados foram preservados; confira a conexão ou use Recuperar."}}
    encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode()) > MAX_RESPONSE:
        encoded = json.dumps({"ok": False, "error": {"code": "response_too_large", "message": "O resultado excede o limite seguro do aplicativo."}})
    sys.stdout.write(encoded + "\n")


if __name__ == "__main__":
    main()
