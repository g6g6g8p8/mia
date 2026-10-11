"""Consistent local SQLite snapshots. Restore only into a new empty directory."""
import argparse
import os
import sqlite3
from pathlib import Path

from .db import database_path


def snapshot(destination: Path) -> None:
    source = database_path()
    if not source.is_file():
        raise ValueError('Instalação não contém banco de dados')
    source_db = sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
    try:
        copy_database(source_db,destination)
    finally:
        source_db.close()


def copy_database(source: sqlite3.Connection, destination: Path) -> None:
    # Exclusive creation prevents overwriting a backup or installation.
    descriptor=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.close(descriptor)
    target=sqlite3.connect(destination)
    try:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('Backup não passou na verificação de integridade')
    finally:
        target.close()


def restore(source: Path, destination: Path) -> None:
    if not source.is_file(): raise ValueError('Backup não encontrado')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Restauração exige diretório vazio; instalação existente não será sobrescrita')
    database=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        if database.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Backup inválido')
        tables={r[0] for r in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'owner','areas','tasks','runs'} <= tables: raise ValueError('Este arquivo não é um backup da Mia')
        destination.mkdir(parents=True,exist_ok=True,mode=0o700)
        copy_database(database,destination/'mia.db')
        with sqlite3.connect(destination/'mia.db') as restored:
            restored.execute('DELETE FROM sessions')
            restored.execute('DELETE FROM login_attempts')
    finally:
        database.close()


def main():
    parser=argparse.ArgumentParser(description='Backup da Mia sem credenciais de API; restauração não sobrescreve instalações.')
    commands=parser.add_subparsers(dest='command',required=True)
    backup=commands.add_parser('backup');backup.add_argument('destination',type=Path)
    recovery=commands.add_parser('restore');recovery.add_argument('source',type=Path);recovery.add_argument('destination',type=Path)
    args=parser.parse_args()
    try:
        if args.command=='backup': snapshot(args.destination)
        else: restore(args.source,args.destination)
    except (ValueError,OSError,sqlite3.Error) as error:
        parser.exit(1,str(error)+'\n')
    print('Concluído. Credenciais de API não estão no backup; ao restaurar, entre novamente e configure sua IA.')


if __name__=='__main__': main()
