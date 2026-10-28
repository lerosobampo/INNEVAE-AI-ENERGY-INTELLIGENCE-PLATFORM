"""Import existing INNEVA.E JSONL runs into SQLite. Safe to repeat."""
from __future__ import annotations
import argparse
import fcntl
import json
from pathlib import Path
from automation_db import DB_PATH, ROOT, initialize, write_run

LOG_DIR = ROOT / 'reports' / 'automation'
LOCK_FILE = LOG_DIR / '.automation_runner.lock'
SOURCE = LOG_DIR / 'runs.jsonl'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=SOURCE)
    args = parser.parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open('a+') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('ERROR: Runner active. Retry when the automation finishes.')
            return 3
        initialize()
        if not args.source.is_file():
            print(f'No historical JSONL file found at {args.source}. Nothing to import.')
            return 0
        # Older JSONL contains RUNNING then final snapshots for the same run.
        # Retain only the latest snapshot, prefer final records.
        records = {}
        invalid = 0
        for line_no, line in enumerate(args.source.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if not isinstance(item, dict) or not item.get('run_id') or not item.get('started_at_utc'):
                    raise ValueError('Missing required run fields')
                rid = item['run_id']
                if rid not in records or item.get('status') != 'RUNNING':
                    records[rid] = item
            except (ValueError, TypeError) as exc:
                invalid += 1
                print(f'SKIPPED malformed line {line_no}: {exc}')
        imported = 0
        for item in records.values():
            # Never overwrite a newer SQLite record with an old JSONL snapshot.
            import sqlite3
            from automation_db import connect
            with connect() as con:
                exists = con.execute('SELECT 1 FROM automation_runs WHERE run_id=?',
                                     (item['run_id'],)).fetchone()
            if exists:
                continue
            write_run(item, imported=True)
            imported += 1
        print(f'IMPORT COMPLETE: {imported} new runs; {len(records)-imported} already present; '
              f'{invalid} malformed lines.')
        print(f'SQLITE: {DB_PATH}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
