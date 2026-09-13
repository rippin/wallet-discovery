"""Run inside the container; creates a transactionally consistent SQLite backup."""
import os
from pathlib import Path
import sqlite3
import sys
if len(sys.argv)!=2:
    raise SystemExit('Usage: python /tmp/backup.py /data/backups/observatory-YYYY-MM-DD.sqlite3')
path=Path(sys.argv[1]);path.parent.mkdir(parents=True,exist_ok=True)
if path.exists():
    raise SystemExit('Refusing to overwrite an existing backup')
source=sqlite3.connect(os.environ.get('OBS_DB','/data/observatory.sqlite3'))
target=sqlite3.connect(path)
with target:
    source.backup(target)
target.close();source.close()
print('Backup written')
