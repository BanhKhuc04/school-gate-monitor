"""Reset stale 'waiting_resource' jobs in training DB — workaround cho smoke test."""
import sqlite3
from app.training import dataset_repo

dsn = dataset_repo.default_db_path()
c = sqlite3.connect(dsn)
cur = c.cursor()
cur.execute(
    "UPDATE dataset_jobs SET state='cancelled', finished_at=datetime('now') "
    "WHERE state IN ('waiting_resource','queued')"
)
print('updated', cur.rowcount)
c.commit()