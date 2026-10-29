#!/usr/bin/env python3
"""Check storage without changing votes or exposing credentials."""
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from app import STORE, load_config, transaction

print(f'Python: {sys.version.split()[0]}')
print(f'UID: {os.geteuid()}, GID: {os.getegid()}')
print(f'Úložiště: {STORE.resolve()}')
for path in (STORE, STORE / 'config.json', STORE / 'state.lock', STORE / 'state.json'):
    try:
        info = path.stat()
        print(f'{path.name}: UID={info.st_uid}, GID={info.st_gid}, práva={info.st_mode & 0o777:o}')
    except FileNotFoundError:
        print(f'{path.name}: neexistuje')
try:
    load_config()
    print('Konfigurace: OK')
    transaction(lambda data: None)
    print('Čtení dat a zamykání: OK')
    with tempfile.TemporaryDirectory(dir=STORE, prefix='check-') as folder:
        source = Path(folder) / 'source'
        target = Path(folder) / 'target'
        source.write_text('check')
        os.replace(source, target)
    print('Zápis a přejmenování: OK')
except Exception as exc:
    print(f'CHYBA: {exc}')
    raise SystemExit(1)
print('Ověřeno pro tohoto uživatele. CGI může běžet pod jiným UID a s jiným BUDGET_STORAGE.')
