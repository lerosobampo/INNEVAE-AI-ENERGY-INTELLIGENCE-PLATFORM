"""INNEVA.E 20.5A — manually process incoming synthetic CSV batches.

Uses existing quality_gated_ingestion.run; writes development CSV only through
that validated path. Maintains independent refresh history in SQLite.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from quality_gated_ingestion import run as quality_gate_run
from incremental_ingestion import PRODUCTION, DEV, digest
from data_quality_db import DEFAULT_DB

REFRESH_ROOT = ROOT / 'data' / 'refresh'
INCOMING = REFRESH_ROOT / 'incoming'
ARCHIVE = REFRESH_ROOT / 'archive'
QUARANTINE = REFRESH_ROOT / 'quarantine'
DB = ROOT / 'reports' / 'data_quality' / 'refresh_history.sqlite3'
LOCK = ROOT / 'reports' / 'data_quality' / '.manual_refresh.lock'

SCHEMA = '''
CREATE TABLE IF NOT EXISTS refresh_attempts (
  attempt_id TEXT PRIMARY KEY,
  attempted_at_utc TEXT NOT NULL,
  candidate_name TEXT NOT NULL,
  candidate_sha256 TEXT NOT NULL,
  status TEXT NOT NULL,
  destination TEXT,
  ingestion_run_id TEXT,
  details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refresh_attempted ON refresh_attempts(attempted_at_utc DESC);
'''


def now():
    return datetime.now(timezone.utc).isoformat()


def db_connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=20)
    conn.execute('PRAGMA busy_timeout=20000')
    conn.executescript(SCHEMA)
    return conn


def save_attempt(db: Path, entry: dict):
    with db_connect(db) as conn:
        conn.execute('''INSERT INTO refresh_attempts
          (attempt_id, attempted_at_utc, candidate_name, candidate_sha256,
           status, destination, ingestion_run_id, details_json)
           VALUES (?,?,?,?,?,?,?,?)''',
          (entry['attempt_id'], entry['attempted_at_utc'], entry['candidate_name'],
           entry['candidate_sha256'], entry['status'], entry.get('destination'),
           entry.get('ingestion_run_id'), json.dumps(entry['details'], default=str)))


def history(db: Path, limit: int):
    if not db.exists():
        return []
    with db_connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('''SELECT attempt_id, attempted_at_utc, candidate_name,
            candidate_sha256, status, destination, ingestion_run_id
            FROM refresh_attempts ORDER BY attempted_at_utc DESC, rowid DESC LIMIT ?''',
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def move_checked(src: Path, destination_dir: Path, expected_digest: str, attempt_id: str):
    if src.is_symlink() or not src.is_file():
        raise RuntimeError('Candidate is no longer a regular file')
    if digest(src) != expected_digest:
        raise RuntimeError('Candidate changed during processing; leaving it in incoming')
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / f'{src.stem}__{attempt_id[:12]}.csv'
    if target.exists():
        raise RuntimeError('Archive destination already exists')
    os.replace(src, target)  # directories are on the same local project volume
    return str(target)


def process_one(candidate: Path, quality_db: Path, refresh_db: Path):
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f'Not a regular CSV: {candidate}')
    if candidate.resolve() in (PRODUCTION.resolve(), DEV.resolve()):
        raise ValueError('Refusing to process production/development as incoming')
    before = digest(candidate)
    prod_before = digest(PRODUCTION)
    entry = {'attempt_id': uuid.uuid4().hex, 'attempted_at_utc': now(),
             'candidate_name': candidate.name, 'candidate_sha256': before}
    try:
        outcome = quality_gate_run(candidate, quality_db)
        status = outcome['status']
        entry['details'] = outcome
        entry['ingestion_run_id'] = outcome.get('ingestion', {}).get('run_id')
        if status == 'APPLIED_WITH_QUALITY_GATE':
            entry['status'] = 'APPLIED'
            entry['destination'] = move_checked(candidate, ARCHIVE, before, entry['attempt_id'])
        elif status == 'REJECTED_QUALITY_GATE':
            entry['status'] = 'REJECTED'
            entry['destination'] = move_checked(candidate, QUARANTINE, before, entry['attempt_id'])
        else:
            # A partial commit must be investigated; keep original input for recovery.
            entry['status'] = 'NEEDS_REVIEW'
            entry['destination'] = str(candidate)
    except Exception as exc:
        entry['status'] = 'ERROR'
        entry['details'] = {'error': f'{type(exc).__name__}: {exc}'}
        entry['destination'] = str(candidate) if candidate.exists() else None
    if digest(PRODUCTION) != prod_before:
        raise RuntimeError('CRITICAL: Production CSV checksum changed')
    save_attempt(refresh_db, entry)
    return {k: v for k, v in entry.items() if k != 'details'} | {'details': entry['details']}


def main():
    parser = argparse.ArgumentParser(description='INNEVA.E manual development data refresh')
    parser.add_argument('--refresh-db', type=Path, default=DB)
    parser.add_argument('--quality-db', type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    sub.add_parser('run')
    h = sub.add_parser('history')
    h.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()
    if args.command == 'history':
        if not 1 <= args.limit <= 1000:
            parser.error('--limit must be 1..1000')
        print(json.dumps({'attempts': history(args.refresh_db, args.limit)}, indent=2))
        return 0
    if args.command == 'status':
        print(json.dumps({'incoming': str(INCOMING),
            'pending_files': sorted(p.name for p in INCOMING.glob('*.csv') if p.is_file() and not p.is_symlink()) if INCOMING.exists() else [],
            'production_rows_unchanged_by_refresh': 'not assessed',
            'recent_attempts': history(args.refresh_db, 5)}, indent=2))
        return 0
    INCOMING.mkdir(parents=True, exist_ok=True)
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open('a+b') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('REFRESH_ERROR: Another manual refresh is already running', file=sys.stderr)
            return 2
        # Order by first UTC hour when possible; invalid files go last.
        candidates = [p for p in INCOMING.glob('*.csv') if p.is_file() and not p.is_symlink()]
        def order_key(p):
            try:
                import pandas as pd
                value = pd.read_csv(p, usecols=['hour_start_utc'], nrows=1).iloc[0, 0]
                return (0, pd.Timestamp(value).tz_convert('UTC').isoformat(), p.name)
            except Exception:
                return (1, '', p.name)
        candidates.sort(key=order_key)
        results = []
        for candidate in candidates:
            results.append(process_one(candidate, args.quality_db, args.refresh_db))
            # Do not attempt later files if one was rejected or encountered an error:
            # later files could be out of sequence after the missing period.
            if results[-1]['status'] != 'APPLIED':
                break
    output = {'status': 'EMPTY' if not results else ('COMPLETE' if all(r['status'] == 'APPLIED' for r in results) else 'STOPPED'),
              'processed': len(results), 'results': results}
    print(json.dumps(output, indent=2, default=str))
    return 0 if output['status'] in ('EMPTY', 'COMPLETE') else 2


if __name__ == '__main__':
    raise SystemExit(main())
