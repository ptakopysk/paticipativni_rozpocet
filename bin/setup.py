#!/usr/bin/env python3
"""Initialize storage, or rotate the administrator password."""
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile

store = Path(os.environ.get('BUDGET_STORAGE', str(Path(__file__).resolve().parent.parent / 'storage')))
store.mkdir(mode=0o700, parents=True, exist_ok=True)
password = getpass.getpass('Heslo správce (alespoň 12 znaků): ')
if len(password) < 12:
    raise SystemExit('Heslo musí mít alespoň 12 znaků.')
if password != getpass.getpass('Heslo znovu: '):
    raise SystemExit('Hesla se neshodují.')
salt = secrets.token_hex(16)
config = {'salt': salt, 'password': hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex(), 'secret': secrets.token_hex(32)}
fd, name = tempfile.mkstemp(dir=store, prefix='config-')
with os.fdopen(fd, 'w') as out:
    json.dump(config, out)
os.replace(name, store / 'config.json')
print(f'Hotovo. Úložiště: {store.resolve()}')
print(f'Setup běžel jako UID {os.geteuid()}. Konfigurace má práva 600; jiný uživatel CGI ji bez úpravy vlastníka nebo práv nepřečte.')
print('Ověření: python3 bin/check.py. Otevřete admin.cgi.')
