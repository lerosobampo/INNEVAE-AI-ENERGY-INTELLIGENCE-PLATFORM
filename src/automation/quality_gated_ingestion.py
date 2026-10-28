"""INNEVA.E 20.3D: development-only ingestion with preflight quality gate.

Run this instead of incremental_ingestion.py apply when quality gating is desired.
Does not modify the production CSV or existing automation scripts.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from incremental_ingestion import (PRODUCTION, DEV, digest, guard_paths,
                                   apply, atomic_copy)
from ingestion_contract import validate_candidate
from data_quality_monitor import analyze
from data_quality_db import DEFAULT_DB, record
from unified_data_loader import load_energy_history

LOCK = HERE.parents[1] / 'reports' / 'data_quality' / '.quality_ingestion.lock'


def run(candidate: Path, db: Path) -> dict:
    guard_paths()
    if candidate.resolve() in (PRODUCTION.resolve(), DEV.resolve()):
        raise ValueError('Candidate cannot be production or development dataset')
    if candidate.is_symlink():
        raise ValueError('Symlinked candidates are not supported')
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open('a+b') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another quality-gated ingestion is running') from exc
        production_before = digest(PRODUCTION)
        # Preflight against development state (or production if development is absent).
        base = DEV if DEV.exists() else PRODUCTION
        base_before = digest(base)
        contract = validate_candidate(candidate, base)
        candidate_before = digest(candidate)
        incoming_quality = analyze(candidate, 'synthetic')
        if incoming_quality['status'] == 'FAIL':
            return {'status': 'REJECTED_QUALITY_GATE', 'stage': 'candidate',
                    'quality': incoming_quality, 'production_unchanged': digest(PRODUCTION) == production_before}
        with tempfile.TemporaryDirectory(prefix='innevae-quality-', dir=LOCK.parent) as tmp:
            combined_path = Path(tmp) / 'combined.csv'
            old = load_energy_history('full_history', base)
            new = pd.read_csv(candidate)
            pd.concat([old, new], ignore_index=True).to_csv(combined_path, index=False)
            combined_quality = analyze(combined_path, 'synthetic')
            if combined_quality['status'] == 'FAIL':
                return {'status': 'REJECTED_QUALITY_GATE', 'stage': 'combined',
                        'quality': combined_quality, 'production_unchanged': digest(PRODUCTION) == production_before}
            # No writes to the development dataset until every preflight check passes.
            if digest(base) != base_before or digest(candidate) != candidate_before:
                raise RuntimeError('Source changed during quality preflight')
            result = apply(candidate)
        # Persist evidence of both input and published dataset. SQLite failure is
        # reported explicitly; it does not pretend the already-applied CSV was rolled back.
        try:
            incoming_assessment = record(candidate, db, 'synthetic')
            published_assessment = record(DEV, db, 'synthetic')
        except Exception as exc:
            return {'status': 'APPLIED_QUALITY_HISTORY_FAILED', 'ingestion': result,
                    'error': f'{type(exc).__name__}: {exc}',
                    'production_unchanged': digest(PRODUCTION) == production_before}
        return {'status': 'APPLIED_WITH_QUALITY_GATE', 'ingestion': result,
                'candidate_quality': incoming_quality['status'],
                'combined_quality': combined_quality['status'],
                'candidate_assessment_id': incoming_assessment['assessment_id'],
                'published_assessment_id': published_assessment['assessment_id'],
                'production_unchanged': digest(PRODUCTION) == production_before}


def main() -> int:
    parser = argparse.ArgumentParser(description='Quality-gated development-only ingestion')
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    try:
        result = run(args.candidate, args.db)
        print(json.dumps(result, indent=2))
        return 0 if result['status'] == 'APPLIED_WITH_QUALITY_GATE' else 2
    except Exception as exc:
        print(f'QUALITY_INGESTION_REJECTED: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
