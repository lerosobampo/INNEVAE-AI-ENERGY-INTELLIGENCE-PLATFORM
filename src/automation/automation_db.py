"""INNEVA.E 19.3: local SQLite automation persistence (stdlib only)."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / 'reports' / 'automation' / 'automation.sqlite3'
JOB_ID = 'historical_energy_manual'


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), timeout=20)
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA busy_timeout=20000')
    con.execute('PRAGMA journal_mode=WAL')
    return con


def initialize():
    with connect() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS automation_jobs (
            job_id TEXT PRIMARY KEY, description TEXT NOT NULL,
            created_at_utc TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1
                CHECK(enabled IN (0,1))
        );
        CREATE TABLE IF NOT EXISTS automation_runs (
            run_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES automation_jobs(job_id),
            started_at_utc TEXT NOT NULL,
            finished_at_utc TEXT,
            status TEXT NOT NULL CHECK(status IN
                ('RUNNING','COMPLETED_VALIDATED','FAILED_VALIDATION','FAILED_EXECUTION','INTERRUPTED')),
            question TEXT NOT NULL,
            dataset_mode TEXT NOT NULL,
            model TEXT NOT NULL,
            historical_data_only INTEGER NOT NULL CHECK(historical_data_only IN (0,1)),
            duration_seconds REAL,
            agent_attempts INTEGER,
            validation_status TEXT,
            validation_json TEXT,
            result_json TEXT,
            error_type TEXT,
            error_message TEXT,
            imported_from_jsonl INTEGER NOT NULL DEFAULT 0 CHECK(imported_from_jsonl IN (0,1))
        );
        CREATE TABLE IF NOT EXISTS automation_run_tools (
            run_id TEXT NOT NULL REFERENCES automation_runs(run_id) ON DELETE CASCADE,
            tool_order INTEGER NOT NULL,
            tool_name TEXT NOT NULL,
            PRIMARY KEY (run_id, tool_order)
        );
        CREATE INDEX IF NOT EXISTS idx_runs_started ON automation_runs(started_at_utc DESC);
        CREATE INDEX IF NOT EXISTS idx_runs_job ON automation_runs(job_id, started_at_utc DESC);
        ''')
        con.execute('INSERT OR IGNORE INTO automation_jobs(job_id,description,created_at_utc) VALUES (?,?,?)',
                    (JOB_ID, 'Manually triggered historical energy analysis', now_utc()))


def ensure_job(con, job_id):
    con.execute('INSERT OR IGNORE INTO automation_jobs(job_id,description,created_at_utc) VALUES (?,?,?)',
                (job_id, 'Historical energy automation', now_utc()))


def write_run(record, imported=False):
    """Insert/update one run and its tool rows in one transaction. Idempotent for migration."""
    validation = record.get('validation') or {}
    status = record.get('status', 'FAILED_EXECUTION')
    if status not in {'RUNNING','COMPLETED_VALIDATED','FAILED_VALIDATION','FAILED_EXECUTION','INTERRUPTED'}:
        raise ValueError(f'Unsupported run status: {status}')
    with connect() as con:
        ensure_job(con, record.get('job_id') or JOB_ID)
        con.execute('''INSERT INTO automation_runs (
            run_id,job_id,started_at_utc,finished_at_utc,status,question,dataset_mode,model,
            historical_data_only,duration_seconds,agent_attempts,validation_status,validation_json,
            result_json,error_type,error_message,imported_from_jsonl)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(run_id) DO UPDATE SET
            finished_at_utc=excluded.finished_at_utc,status=excluded.status,
            duration_seconds=excluded.duration_seconds,agent_attempts=excluded.agent_attempts,
            validation_status=excluded.validation_status,validation_json=excluded.validation_json,
            result_json=excluded.result_json,error_type=excluded.error_type,
            error_message=excluded.error_message,
            imported_from_jsonl=MAX(automation_runs.imported_from_jsonl,excluded.imported_from_jsonl)
            ''', (
                record['run_id'], record.get('job_id') or JOB_ID, record['started_at_utc'],
                record.get('finished_at_utc'), status, record.get('question') or '(unknown)',
                record.get('dataset_mode') or 'unknown', record.get('model') or 'unknown',
                int(bool(record.get('historical_data_only', True))), record.get('duration_seconds'),
                record.get('agent_attempts'), validation.get('status'),
                json.dumps(record.get('validation'), ensure_ascii=False, default=str),
                json.dumps(record.get('result'), ensure_ascii=False, default=str),
                record.get('error_type'), record.get('error_message'), int(imported)
            ))
        con.execute('DELETE FROM automation_run_tools WHERE run_id=?', (record['run_id'],))
        for i, tool in enumerate(record.get('selected_tools') or [], 1):
            con.execute('INSERT INTO automation_run_tools(run_id,tool_order,tool_name) VALUES (?,?,?)',
                        (record['run_id'], i, str(tool)))


def recent_runs(limit=10):
    with connect() as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute('''
            SELECT run_id,job_id,started_at_utc,finished_at_utc,status,dataset_mode,
                   model,duration_seconds,validation_status,error_type
            FROM automation_runs ORDER BY started_at_utc DESC LIMIT ?''', (limit,))]


def recover_interrupted():
    """Call only while holding the exclusive runner lock."""
    with connect() as con:
        return con.execute('''UPDATE automation_runs SET status='INTERRUPTED',
            finished_at_utc=?, error_type='InterruptedRun',
            error_message='Previous runner exited before recording completion'
            WHERE status='RUNNING' ''', (now_utc(),)).rowcount
