"""INNEVA.E checkpoint 19.6: isolated reliability tests; never writes to project DB.

Run from the project root: python3 src/automation/reliability_test.py
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[2]
SOURCE = PROJECT / 'src' / 'automation'
AGENT_STUB = '''import os

def run_dynamic_agent(question, mode, model):
    scenario = os.environ.get('INNEVAE_TEST_SCENARIO', 'success')
    if scenario == 'slow':
        time.sleep(3)
    if scenario == 'exception':
        raise ConnectionError('Simulated Ollama unavailable')
    if scenario == 'invalid':
        return {'status': 'completed', 'validation': {'status': 'fail'},
                'selected_tools': ['get_energy_overview'], 'attempts': 1,
                'response': 'Simulated invalid response'}
    return {'status': 'completed', 'validation': {'status': 'pass'},
            'selected_tools': ['get_energy_overview', 'get_data_quality', 'forecast_next_hour'],
            'attempts': 1, 'response': 'Synthetic validated test result'}
'''


def execute(runner, scenario='success'):
    env = os.environ.copy()
    env['INNEVAE_TEST_SCENARIO'] = scenario
    return subprocess.run([sys.executable, str(runner)], env=env,
                          text=True, capture_output=True, timeout=20)


def rows(db):
    with sqlite3.connect(db) as conn:
        return conn.execute('SELECT run_id,status,error_type,validation_status FROM automation_runs ORDER BY rowid').fetchall()


def check(condition, label, detail=''):
    print(f"{'PASS' if condition else 'FAIL'} | {label}" + (f' | {detail}' if detail else ''), flush=True)
    return bool(condition)


def main():
    for name in ('automation_runner.py', 'automation_db.py'):
        if not (SOURCE / name).is_file():
            print(f'MISSING: {SOURCE / name}')
            return 2
    results = []
    with tempfile.TemporaryDirectory(prefix='innevae_reliability_') as folder:
        root = Path(folder)
        automation = root / 'src' / 'automation'
        agents = root / 'src' / 'agents'
        automation.mkdir(parents=True)
        agents.mkdir(parents=True)
        for name in ('automation_runner.py', 'automation_db.py'):
            shutil.copy2(SOURCE / name, automation / name)
        (agents / 'dynamic_energy_agent.py').write_text(AGENT_STUB, encoding='utf-8')
        runner = automation / 'automation_runner.py'
        db = root / 'reports' / 'automation' / 'automation.sqlite3'

        ok = execute(runner, 'success')
        results.append(check(ok.returncode == 0 and 'COMPLETED_VALIDATED' in ok.stdout,
                             'Validated result accepted', f'exit={ok.returncode}'))
        initial = rows(db)
        results.append(check(len(initial) == 1 and initial[0][1] == 'COMPLETED_VALIDATED',
                             'Validated execution persisted'))

        bad = execute(runner, 'invalid')
        current = rows(db)
        results.append(check(bad.returncode == 2 and current[-1][1] == 'FAILED_VALIDATION',
                             'Invalid result rejected and persisted', f'exit={bad.returncode}'))

        failed = execute(runner, 'exception')
        current = rows(db)
        results.append(check(failed.returncode == 1 and current[-1][1] == 'FAILED_EXECUTION'
                             and current[-1][2] == 'ConnectionError',
                             'Ollama exception persisted', f'exit={failed.returncode}'))

        # Hold the real lock file in this test process, then try a second run.
        lock_path = root / 'reports' / 'automation' / '.automation_runner.lock'
        with lock_path.open('a+') as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                second = execute(runner, 'success')
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        results.append(check(second.returncode == 3 and 'SKIPPED_DUPLICATE' in second.stdout,
                             'Concurrent run prevented', f'exit={second.returncode}'))

        # Simulate a prior process dying after persisting RUNNING. The next
        # lock holder should mark it INTERRUPTED before executing normally.
        with sqlite3.connect(db) as conn:
            conn.execute("""INSERT INTO automation_runs
                (run_id,job_id,started_at_utc,status,question,dataset_mode,model,historical_data_only)
                VALUES ('synthetic_stale_run','historical_energy_manual',
                '2026-01-01T00:00:00+00:00','RUNNING','synthetic','development_90d','stub',1)""")
        recovered = execute(runner, 'success')
        with sqlite3.connect(db) as conn:
            stale = conn.execute("SELECT status,error_type FROM automation_runs WHERE run_id='synthetic_stale_run'").fetchone()
        results.append(check(recovered.returncode == 0 and stale == ('INTERRUPTED', 'InterruptedRun'),
                             'Interrupted run recovered', f'stale={stale}'))

        with sqlite3.connect(db) as conn:
            bad_approved = conn.execute("""SELECT COUNT(*) FROM automation_runs
                WHERE status='COMPLETED_VALIDATED' AND validation_status != 'pass'""").fetchone()[0]
            statuses = conn.execute('SELECT status,COUNT(*) FROM automation_runs GROUP BY status').fetchall()
        results.append(check(bad_approved == 0, 'Validation gate integrity'))
        print('ISOLATED DATABASE STATUS COUNTS:', dict(statuses))
        print('Project SQLite and JSONL were not accessed by the test runners.')
    print(f'RESULT: {sum(results)}/{len(results)} tests passed')
    return 0 if all(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
