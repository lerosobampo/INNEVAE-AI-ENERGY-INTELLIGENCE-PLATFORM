"""INNEVA.E checkpoint 20.2: safe development-only incremental CSV ingestion.

Never writes the production canonical CSV. Supports apply, verify and rollback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src' / 'automation'))
sys.path.insert(0, str(ROOT / 'src' / 'forecasting'))
from ingestion_contract import validate_candidate
from unified_data_loader import load_energy_history, EXPECTED_COLUMNS

PRODUCTION = ROOT / 'data' / 'forecasting' / 'energy_intelligence_hourly.csv'
DEV = ROOT / 'data' / 'staging' / 'energy_intelligence_hourly_development.csv'
BACKUPS = ROOT / 'data' / 'staging' / 'backups'
AUDIT = ROOT / 'reports' / 'automation' / 'ingestion_audit.jsonl'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.ingest-', suffix='.csv', dir=dst.parent)
    try:
        with os.fdopen(fd, 'wb') as out, src.open('rb') as inp:
            shutil.copyfileobj(inp, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, dst)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def atomic_dataframe(df, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.ingest-', suffix='.csv', dir=dst.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as out:
            df.to_csv(out, index=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, dst)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def log_event(event):
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'at_utc': datetime.now(timezone.utc).isoformat(), **event}) + '\n')
        f.flush()
        os.fsync(f.fileno())


def guard_paths():
    if DEV.resolve() == PRODUCTION.resolve():
        raise ValueError('Development and production paths must differ')
    if DEV.is_symlink() or PRODUCTION.is_symlink():
        raise ValueError('Symlinked dataset paths are not supported')


def apply(candidate):
    guard_paths()
    if not PRODUCTION.is_file():
        raise FileNotFoundError(PRODUCTION)
    production_before = digest(PRODUCTION)
    if not DEV.exists():
        atomic_copy(PRODUCTION, DEV)
        log_event({'event': 'INITIALIZE_DEVELOPMENT', 'rows': len(load_energy_history('full_history', DEV))})
    check = validate_candidate(candidate, DEV)
    before = digest(DEV)
    previous = load_energy_history('full_history', DEV)
    incoming = pd.read_csv(candidate)
    if list(incoming.columns) != list(EXPECTED_COLUMNS):
        raise ValueError('Unexpected candidate schema')
    combined = pd.concat([previous, incoming], ignore_index=True)
    # Validate the complete output before publishing it.
    with tempfile.TemporaryDirectory(dir=DEV.parent) as tmp:
        staged = Path(tmp) / 'combined.csv'
        combined.to_csv(staged, index=False)
        checked = load_energy_history('full_history', staged)
        if len(checked) != len(previous) + len(incoming):
            raise ValueError('Merged row count mismatch')
        run_id = uuid.uuid4().hex
        BACKUPS.mkdir(parents=True, exist_ok=True)
        backup = BACKUPS / f'{run_id}_before.csv'
        atomic_copy(DEV, backup)
        if digest(backup) != before:
            raise RuntimeError('Backup verification failed')
        atomic_copy(staged, DEV)
    if digest(PRODUCTION) != production_before:
        raise RuntimeError('PRODUCTION DATASET CHANGED: investigate immediately')
    result = {'status': 'APPLIED_DEVELOPMENT_ONLY', 'run_id': run_id,
              'previous_rows': len(previous), 'appended_rows': len(incoming),
              'new_rows': len(checked), 'backup': str(backup),
              'development_dataset': str(DEV), 'production_unchanged': True,
              'development_sha256_before': before, 'development_sha256_after': digest(DEV),
              'candidate_first_hour_utc': check['first_new_hour_utc']}
    log_event({'event': 'APPLY', **result})
    return result


def rollback(run_id):
    guard_paths()
    if not run_id or any(c not in '0123456789abcdef' for c in run_id) or len(run_id) != 32:
        raise ValueError('Invalid run ID')
    backup = BACKUPS / f'{run_id}_before.csv'
    if not backup.is_file() or not DEV.is_file():
        raise FileNotFoundError('Development dataset or requested backup not found')
    # Only roll back the latest applied state; never overwrite subsequent ingestion.
    events = [json.loads(line) for line in AUDIT.read_text().splitlines() if line.strip()]
    changes = [e for e in events if e.get('event') in {'APPLY', 'ROLLBACK'}]
    if not changes or changes[-1].get('event') != 'APPLY' or changes[-1].get('run_id') != run_id:
        raise ValueError('Rollback allowed only for the most recent unrolled-back ingestion')
    if digest(DEV) != changes[-1]['development_sha256_after']:
        raise ValueError('Development dataset changed since ingestion; refusing rollback')
    if digest(backup) != changes[-1]['development_sha256_before']:
        raise ValueError('Backup checksum mismatch')
    production_before = digest(PRODUCTION)
    atomic_copy(backup, DEV)
    if digest(PRODUCTION) != production_before:
        raise RuntimeError('Production dataset changed unexpectedly')
    result = {'status': 'ROLLED_BACK_DEVELOPMENT_ONLY', 'run_id': run_id,
              'rows': len(load_energy_history('full_history', DEV)), 'production_unchanged': True}
    log_event({'event': 'ROLLBACK', **result})
    return result


def main():
    parser = argparse.ArgumentParser(description='Safe local development-only ingestion')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('apply')
    p.add_argument('--candidate', type=Path, required=True)
    r = sub.add_parser('rollback')
    r.add_argument('--run-id', required=True)
    sub.add_parser('status')
    args = parser.parse_args()
    try:
        if args.command == 'apply':
            result = apply(args.candidate)
        elif args.command == 'rollback':
            result = rollback(args.run_id)
        else:
            result = {'status': 'DEVELOPMENT_EXISTS' if DEV.exists() else 'NOT_INITIALIZED',
                      'production_rows': len(load_energy_history('full_history', PRODUCTION)),
                      'development_rows': len(load_energy_history('full_history', DEV)) if DEV.exists() else None,
                      'production_sha256': digest(PRODUCTION)}
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f'INGESTION_REJECTED: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
