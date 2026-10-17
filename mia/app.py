from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from . import __version__
from .db import data_dir, initialize
from . import backup_jobs, migrations

from .http_dependencies import SAFE_METHODS, STATIC
# Preserve imports used by integrations and the existing test suite.
from .http_dependencies import EXPORT_LOCK as EXPORT_LOCK
from .http_schemas import TaskInput as TaskInput

from .routers import auth, tasks, areas, sources, ai, system


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize()
    directory = data_dir()
    migrations.initialize(directory)
    stop = asyncio.Event()
    tasks = [asyncio.create_task(backup_jobs.worker(stop)),
             asyncio.create_task(migrations.worker(stop, directory))]
    try:
        yield
    finally:
        stop.set()
        await asyncio.gather(*tasks)


app = FastAPI(title="Mia", version=__version__, lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def safe_validation(request: Request, error: RequestValidationError):
    return JSONResponse({'detail':[{'loc':item['loc'],'msg':item['msg']} for item in error.errors()]},status_code=422)


@app.middleware("http")
async def limit_upload(request: Request, call_next):
    managed_root = os.environ.get('MIA_OPERATIONS_ROOT')
    if managed_root and request.method not in SAFE_METHODS:
        try:
            maintenance = (Path(managed_root) / 'journal.json').exists()
        except OSError:
            maintenance = True
        if maintenance:
            return JSONResponse({'detail': 'Atualização ou recuperação em andamento. Aguarde a conclusão no terminal antes de alterar dados.'}, status_code=503, headers={'Retry-After':'5', 'Cache-Control':'no-store'})
    if request.url.path == '/api/imports' and request.method == 'POST':
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 12_000_000:
                return JSONResponse({'detail':'Upload excede o limite de 8 MB (12 MB codificado)'},status_code=413)
            body.extend(chunk)
        request._body = bytes(body)
    return await call_next(request)


for router in (auth.router, tasks.router, areas.router, sources.router, ai.router, system.router):
    app.include_router(router)


app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")
