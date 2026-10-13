#!/usr/bin/env python3
"""Offline synthetic migration benchmark with a real HTTP server and worker.

Corpus and gates are declared before a run: 1,000/1,500 notes, 20 MiB of
eligible UTF-8 text, stored ZIP plus ignored metadata/media. No personal sources
or models are used. Server affinity is limited to two CPUs where supported;
four GiB address-space limit is reported separately from physical host memory.
Measure network transfer separately from inventory and authorized indexing.

Usage: python scripts/benchmark_migration.py --notes 1000 1500
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import socket
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

import httpx

ROOT = Path(__file__).resolve().parents[1]
TEXT_BYTES = 20 * 1024 * 1024
GATES = dict(first_searchable_seconds=60, indexing_seconds=600,
             server_peak_rss_bytes=1024 * 1024 * 1024,
             authenticated_today_p95_ms=250)


def corpus(path, notes, text_bytes):
    per_note = text_bytes // notes
    if per_note > 8 * 1024 * 1024:
        raise ValueError('Synthetic note exceeds the supported per-note bound')
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as output:
        for number in range(notes):
            header = f'# Synthetic project {number}\n\n'
            tail = f'\n\nBENCHMARK_DECISION: synthetic decision {number}; factual source at the end.\n'
            filler = 'Earlier synthetic background about an unrelated topic. '
            target = per_note + (1 if number < text_bytes % notes else 0)
            remaining = max(0, target-len(header.encode())-len(tail.encode()))
            content = header + (filler * math.ceil(remaining / len(filler)))[:remaining] + tail
            output.writestr(f'Vault/Projects/{number % 20:02}/note-{number:05}.md', content)
        output.writestr('Vault/', '')
        output.writestr('Vault/.obsidian/preferences.json', '{"synthetic":true}')
        output.writestr('Vault/.git/config', 'synthetic metadata')
        output.writestr('Vault/picture.png', b'synthetic ignored media')


def rss(pid):
    if sys.platform.startswith('linux'):
        try:
            for line in Path(f'/proc/{pid}/status').read_text().splitlines():
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) * 1024
        except FileNotFoundError:
            return 0
    value = subprocess.run(['ps', '-o', 'rss=', '-p', str(pid)], capture_output=True, text=True)
    return int(value.stdout.strip() or '0') * 1024


def disk(directory):
    total = 0
    for path in directory.rglob('*'):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except FileNotFoundError:
            pass
    return total


def response(result):
    result.raise_for_status()
    return result.json()


def case(notes, text_bytes):
    available = sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else []
    cpu_set = available[:2]
    address_space = 4 * 1024 * 1024 * 1024

    def constraints():
        if cpu_set:
            os.sched_setaffinity(0, cpu_set)
        resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))

    with tempfile.TemporaryDirectory(prefix='mia-synthetic-benchmark-') as temporary:
        directory = Path(temporary)
        data = directory / 'data'
        data.mkdir(mode=0o700)
        source = directory / 'synthetic-vault.zip'
        corpus(source, notes, text_bytes)
        digest = hashlib.sha256()
        with source.open('rb') as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b''):
                digest.update(chunk)
        with socket.socket() as socket_probe:
            socket_probe.bind(('127.0.0.1', 0))
            port = socket_probe.getsockname()[1]
        environment = {**os.environ, 'MIA_DATA_DIR': str(data), 'MIA_AI_ENABLED': 'false',
                       'MIA_COOKIE_SECURE': 'false', 'PYTHONPATH': str(ROOT)}
        log = (directory / 'server.log').open('w')
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'mia.app:app',
                                    '--host', '127.0.0.1', '--port', str(port), '--log-level', 'warning'],
                                   cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                   preexec_fn=constraints if os.name == 'posix' else None)
        stop = threading.Event()
        measurements = {'server_peak_rss_bytes': 0}

        def sample_memory():
            while not stop.wait(.05):
                measurements['server_peak_rss_bytes'] = max(measurements['server_peak_rss_bytes'], rss(process.pid))

        sampler = threading.Thread(target=sample_memory, daemon=True)
        sampler.start()
        latencies = []
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=60) as browser:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        response(browser.get('/health'))
                        break
                    except httpx.TransportError:
                        if process.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError('Synthetic HTTP server did not start')
                        time.sleep(.05)
                response(browser.post('/api/setup', json={'name': 'Synthetic benchmark', 'email': '',
                            'timezone': 'UTC', 'password': 'synthetic-benchmark-password', 'area_name': 'Projects'}))
                job = response(browser.post('/api/migrations', json={'filename': 'synthetic-vault.zip',
                            'size': source.stat().st_size, 'sha256': digest.hexdigest(), 'source_kind': 'obsidian'}))
                job_id = job['id']
                transfer_started = time.monotonic()
                with source.open('rb') as file:
                    offset = 0
                    while chunk := file.read(job['limits']['chunk_bytes']):
                        response(browser.put(f'/api/migrations/{job_id}/upload', params={'offset': offset}, content=chunk))
                        offset += len(chunk)
                response(browser.post(f'/api/migrations/{job_id}/finish'))
                transfer_seconds = time.monotonic() - transfer_started
                inventory_started = time.monotonic()
                deadline = inventory_started + 600
                while True:
                    job = response(browser.get(f'/api/migrations/{job_id}', params={'limit': 1}))
                    started = time.monotonic()
                    response(browser.get('/api/today'))
                    latencies.append((time.monotonic() - started) * 1000)
                    if job['state'] == 'review':
                        break
                    if job['state'] in ('failed', 'cancelled') or time.monotonic() > deadline:
                        raise RuntimeError(f"Inventory failed: {job.get('error')}")
                    time.sleep(.1)
                inventory_seconds = time.monotonic() - inventory_started
                disk_peak = disk(data)
                assert job['report']['recognized'] == notes and job['report']['entries']['ignored'] == 3
                indexing_started = time.monotonic()
                response(browser.post(f'/api/migrations/{job_id}/confirm', json={'groups': ['*'], 'excluded_ids': []}))
                first_searchable = None
                deadline = indexing_started + 600
                while True:
                    started = time.monotonic()
                    response(browser.get('/api/today'))
                    latencies.append((time.monotonic() - started) * 1000)
                    if first_searchable is None:
                        found = response(browser.get('/api/search', params={'q': 'BENCHMARK_DECISION'}))
                        if found['results']:
                            first_searchable = time.monotonic() - indexing_started
                    job = response(browser.get(f'/api/migrations/{job_id}', params={'limit': 1}))
                    disk_peak = max(disk_peak, disk(data))
                    if job['state'] in ('completed', 'partial'):
                        break
                    if job['state'] in ('failed', 'cancelled') or time.monotonic() > deadline:
                        raise RuntimeError(f"Indexing failed: {job.get('error')}")
                    time.sleep(.1)
                indexing_seconds = time.monotonic() - indexing_started
                assert job['report']['indexed'] == notes and job['report']['imported'] == notes
                ordered = sorted(latencies)
                p95 = ordered[min(len(ordered)-1, math.ceil(.95 * len(ordered))-1)]
                values = {**measurements, 'notes': notes, 'eligible_text_bytes': text_bytes,
                          'upload_bytes': source.stat().st_size, 'transfer_seconds': round(transfer_seconds, 3),
                          'inventory_seconds': round(inventory_seconds, 3),
                          'first_searchable_seconds': round(first_searchable or indexing_seconds, 3),
                          'indexing_seconds': round(indexing_seconds, 3),
                          'authenticated_today_p95_ms': round(p95, 3),
                          'api_samples': len(latencies), 'server_disk_peak_bytes': disk_peak,
                          'server_disk_final_bytes': disk(data), 'report': job['report'],
                          'resources': {'server_cpu_affinity': cpu_set or 'not constrained',
                                        'server_address_space_limit_bytes': address_space,
                                        'rss_scope': 'one real uvicorn process, API and import worker',
                                        'network_scope': 'loopback HTTP, measured separately',
                                        'platform': platform.platform(), 'python': platform.python_version()},
                          'gates': GATES}
                values['gates_passed'] = all(values[name] <= bound for name, bound in GATES.items())
                return values
        finally:
            stop.set()
            sampler.join(timeout=2)
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--notes', type=int, nargs='+', default=[1000, 1500])
    parser.add_argument('--text-bytes', type=int, default=TEXT_BYTES)
    args = parser.parse_args()
    if any(number < 1 or number > 10_000 for number in args.notes):
        parser.error('Use 1 to 10,000 synthetic notes')
    results = [case(number, args.text_bytes) for number in args.notes]
    print(json.dumps({'format': 'mia-synthetic-migration-benchmark/1', 'results': results}, ensure_ascii=False, indent=2))
    return 0 if all(result['gates_passed'] for result in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
