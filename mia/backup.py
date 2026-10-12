"""Consistent local SQLite snapshots. Restore only into a new empty directory."""
import argparse
import os
import sqlite3
import tempfile
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
    try:
        target=sqlite3.connect(destination)
        try:
            source.backup(target)
            validate_database(target)
        finally:
            target.close()
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def validate_database(database: sqlite3.Connection) -> None:
    if database.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
        raise ValueError('Backup não passou na verificação de integridade')
    tables={r[0] for r in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'owner','areas','tasks','runs','sessions','login_attempts'} <= tables:
        raise ValueError('Este arquivo não é um backup da Mia')
    if database.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise ValueError('Backup contém referências inválidas')


def verify(source: Path) -> None:
    if not source.is_file():
        raise ValueError('Backup não encontrado')
    database=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        validate_database(database)
    finally:
        database.close()


def restore(source: Path, destination: Path) -> None:
    if not source.is_file(): raise ValueError('Backup não encontrado')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Restauração exige diretório vazio; instalação existente não será sobrescrita')
    database=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        validate_database(database)
        destination.mkdir(parents=True,exist_ok=True,mode=0o700)
        # Publish only a complete, sanitized database. Hard-link creation is
        # atomic and refuses an existing database, including one created meanwhile.
        with tempfile.TemporaryDirectory(prefix='.mia-restore-',dir=destination) as staging:
            staged=Path(staging)/'mia.db'
            copy_database(database,staged)
            restored=sqlite3.connect(staged)
            try:
                with restored:
                    restored.execute('DELETE FROM sessions')
                    restored.execute('DELETE FROM login_attempts')
                restored.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                restored.execute('PRAGMA journal_mode=DELETE')
                validate_database(restored)
            finally:
                restored.close()
            os.link(staged,destination/'mia.db')
    finally:
        database.close()


def main():
    parser=argparse.ArgumentParser(description='Backup da Mia sem credenciais de API; restauração não sobrescreve instalações.')
    commands=parser.add_subparsers(dest='command',required=True)
    backup=commands.add_parser('backup');backup.add_argument('destination',type=Path)
    check=commands.add_parser('verify');check.add_argument('source',type=Path)
    recovery=commands.add_parser('restore');recovery.add_argument('source',type=Path);recovery.add_argument('destination',type=Path)
    args=parser.parse_args()
    try:
        if args.command=='backup': snapshot(args.destination)
        elif args.command=='verify': verify(args.source)
        else: restore(args.source,args.destination)
    except (ValueError,OSError,sqlite3.Error) as error:
        parser.exit(1,str(error)+'\n')
    if args.command=='verify':
        print('Backup verificado: integridade, tabelas essenciais e referências válidas. Faça também um ensaio de restauração.')
    else:
        print('Concluído. Credenciais de API não estão no backup; ao restaurar, entre novamente e configure sua IA.')


if __name__=='__main__': main()
