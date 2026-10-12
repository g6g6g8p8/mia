"""Exercise installed wheel assets and HTTP startup, without source-path imports."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

with socket.socket() as probe:
    probe.bind(('127.0.0.1',0))
    port=probe.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='mia-package-') as temporary:
    env={**os.environ,'MIA_DATA_DIR':temporary,'MIA_AI_ENABLED':'false','MIA_COOKIE_SECURE':'false'}
    env.pop('PYTHONPATH',None)
    with (Path(temporary)/'server.log').open('w+') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','mia.app:app','--host','127.0.0.1','--port',str(port)],cwd=temporary,env=env,stdout=log,stderr=log)
        try:
            origin=f'http://127.0.0.1:{port}'
            for _ in range(100):
                try:
                    with urllib.request.urlopen(origin+'/health',timeout=1) as response:
                        assert response.status==200
                    break
                except OSError:
                    if server.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    time.sleep(.1)
            else:
                raise RuntimeError('Installed package did not start')
            for path in ['/', '/assets/app.js', '/assets/app.css', '/assets/mia-icon.svg', '/assets/ai-setup.js', '/assets/access.js', '/assets/personalization.js']:
                with urllib.request.urlopen(origin+path,timeout=3) as response:
                    assert response.status==200 and response.read(),path
            print('PASS: installed package starts over HTTP and serves all interface modules offline')
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
