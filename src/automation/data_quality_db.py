"""INNEVA.E checkpoint 20.3C: independent SQLite history for data quality.

Reads datasets without changing them. Writes ONLY to the specified quality SQLite DB.
Exit: 0 PASS/WARNING, 2 FAIL/invalid dataset, 1 infrastructure error.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / 'reports' / 'data_quality' / 'quality_history.sqlite3'
DEFAULT_DATASET = ROOT / 'data' / 'forecasting' / 'energy_intelligence_hourly.csv'

# Import the existing, read-only quality engine without altering it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_quality_monitor import analyze

SCHEMA = '''
CREATE TABLE IF NOT EXISTS quality_assessments (
  assessment_id TEXT PRIMARY KEY,
  assessed_at_utc TEXT NOT NULL,
  dataset_path TEXT NOT NULL,
  dataset_sha256 TEXT NOT NULL,
  source_kind TEXT NOT NULL CHECK(source_kind IN ('historical','synthetic')),
  status TEXT NOT NULL CHECK(status IN ('PASS','WARNING','FAIL')),
  rows INTEGER NOT NULL,
  columns INTEGER NOT NULL,
  first_hour_utc TEXT,
  last_hour_utc TEXT,
  fail_count INTEGER NOT NULL,
  warning_count INTEGER NOT NULL,
  report_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quality_assessed ON quality_assessments(assessed_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_quality_dataset ON quality_assessments(dataset_path, assessed_at_utc DESC);
CREATE TABLE IF NOT EXISTS quality_issues (
  assessment_id TEXT NOT NULL REFERENCES quality_assessments(assessment_id) ON DELETE CASCADE,
  issue_order INTEGER NOT NULL,
  severity TEXT NOT NULL,
  check_name TEXT NOT NULL,
  affected_count INTEGER NOT NULL,
  detail TEXT NOT NULL,
  PRIMARY KEY (assessment_id, issue_order)
);
'''

def connect(db: Path):
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db), timeout=20)
    con.execute('PRAGMA busy_timeout=20000')
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA journal_mode=WAL')
    con.executescript(SCHEMA)
    return con

def checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def record(dataset: Path, db: Path, source_kind: str) -> dict:
    # Check source integrity before and after analysis to avoid recording a mixed snapshot.
    before = checksum(dataset)
    report = analyze(dataset, source_kind)
    after = checksum(dataset)
    if before != after:
        raise RuntimeError('Dataset changed while being analyzed; assessment not recorded')
    aid = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    with connect(db) as con:
        with con:
            con.execute('''INSERT INTO quality_assessments
              (assessment_id,assessed_at_utc,dataset_path,dataset_sha256,source_kind,
               status,rows,columns,first_hour_utc,last_hour_utc,fail_count,warning_count,report_json)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (aid,timestamp,str(dataset.resolve()),before,source_kind,report['status'],
               report['rows'],report['columns'],report['first_hour_utc'],report['last_hour_utc'],
               report['counts']['fail'],report['counts']['warning'],json.dumps(report,allow_nan=False)))
            con.executemany('''INSERT INTO quality_issues
              (assessment_id,issue_order,severity,check_name,affected_count,detail)
              VALUES (?,?,?,?,?,?)''',
              [(aid,i,x['severity'],x['check'],x['count'],x['detail'])
               for i,x in enumerate(report['issues'])])
    return {'assessment_id':aid,'assessed_at_utc':timestamp,'status':report['status'],
            'dataset_sha256':before,'rows':report['rows'],
            'fail_count':report['counts']['fail'],'warning_count':report['counts']['warning'],
            'issues_saved':len(report['issues']),'database':str(db.resolve())}

def history(db: Path, limit: int) -> dict:
    if not db.is_file():
        return {'status':'NOT_INITIALIZED','assessments':[]}
    with connect(db) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute('''SELECT assessment_id,assessed_at_utc,dataset_path,dataset_sha256,
            source_kind,status,rows,fail_count,warning_count FROM quality_assessments
            ORDER BY assessed_at_utc DESC, rowid DESC LIMIT ?''',(limit,)).fetchall()
    return {'status':'OK','assessments':[dict(r) for r in rows]}

def detail(db: Path, assessment_id: str) -> dict:
    if not db.is_file():
        raise ValueError('Quality database not initialized')
    with connect(db) as con:
        row = con.execute('SELECT report_json FROM quality_assessments WHERE assessment_id=?',
                          (assessment_id,)).fetchone()
    if row is None:
        raise ValueError('Assessment not found')
    return json.loads(row[0])

def main() -> int:
    p = argparse.ArgumentParser(description='INNEVA.E SQLite data-quality assessment history')
    p.add_argument('--db',type=Path,default=DEFAULT_DB,help='Separate quality-history SQLite file')
    sub = p.add_subparsers(dest='command',required=True)
    r = sub.add_parser('record',help='Analyze dataset and persist one immutable assessment')
    r.add_argument('--dataset',type=Path,default=DEFAULT_DATASET)
    r.add_argument('--source-kind',choices=['historical','synthetic'],default='historical')
    h = sub.add_parser('history',help='Show recent assessments')
    h.add_argument('--limit',type=int,default=10)
    d = sub.add_parser('detail',help='Retrieve original quality report')
    d.add_argument('--assessment-id',required=True)
    args = p.parse_args()
    try:
        if args.command == 'record':
            result = record(args.dataset,args.db,args.source_kind)
            print(json.dumps(result,indent=2))
            return 2 if result['status']=='FAIL' else 0
        if args.command == 'history':
            if not 1 <= args.limit <= 1000:
                raise ValueError('--limit must be between 1 and 1000')
            print(json.dumps(history(args.db,args.limit),indent=2))
            return 0
        print(json.dumps(detail(args.db,args.assessment_id),indent=2))
        return 0
    except (ValueError,FileNotFoundError,sqlite3.Error,RuntimeError) as exc:
        print(f'QUALITY_HISTORY_ERROR: {type(exc).__name__}: {exc}',file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
