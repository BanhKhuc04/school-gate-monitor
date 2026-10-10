"""Back up and upgrade runtime reviews and training schemas.

Run: python -m scripts.migrate_ocr_training
Use --app-db and --training-db to verify an isolated/new installation.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def migrate(app_db: Path, training_db: Path, backup_dir: Path) -> None:
    from app import db
    from app.training import dataset_repo

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for label, path in [('app', app_db), ('training', training_db)]:
        if path.is_file():
            backup_dir.mkdir(parents=True, exist_ok=True)
            destination = backup_dir / f'{label}_{stamp}.db'
            with sqlite3.connect(str(path)) as source, sqlite3.connect(str(destination)) as target:
                source.backup(target)
            print(f'Backup: {destination}')
    original = db.DB_PATH
    try:
        db.DB_PATH = str(app_db)
        db.init_db()
    finally:
        db.DB_PATH = original
    dataset_repo.init_db(str(training_db))
    for label, path in [('app', app_db), ('training', training_db)]:
        with sqlite3.connect(str(path)) as conn:
            check = conn.execute('PRAGMA integrity_check').fetchone()[0]
            if check != 'ok':
                raise RuntimeError(f'{label} integrity check: {check}')
        print(f'Migrated: {path} (integrity ok)')


def main() -> None:
    from app.config import BASE_DIR, DB_PATH
    from app.training.dataset_repo import default_db_path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-db', type=Path, default=Path(DB_PATH))
    parser.add_argument('--training-db', type=Path, default=Path(default_db_path()))
    parser.add_argument('--backup-dir', type=Path, default=BASE_DIR / 'data' / 'backups' / 'schema')
    args = parser.parse_args()
    migrate(args.app_db.resolve(), args.training_db.resolve(), args.backup_dir.resolve())


if __name__ == '__main__':
    main()
