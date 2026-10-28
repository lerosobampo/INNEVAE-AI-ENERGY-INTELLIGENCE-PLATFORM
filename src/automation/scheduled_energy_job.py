"""INNEVA.E 19.7.1: manual-first, launchd-ready orchestration.

Does not install or enable a schedule. Existing runner, DB and report generator
remain unchanged. Run --dry-run first; --run invokes the local AI once.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / 'src' / 'automation' / 'automation_runner.py'
REPORTER = ROOT / 'src' / 'automation' / 'report_generator.py'
DATABASE = ROOT / 'reports' / 'automation' / 'automation.sqlite3'
UUID_PATTERN = re.compile(r'\brun=([0-9a-fA-F-]{36})\b')


def execute(*, dry_run: bool) -> int:
    if not RUNNER.is_file() or not REPORTER.is_file():
        print('ERROR: Missing automation_runner.py or report_generator.py', flush=True)
        return 4
    print(f'PROJECT: {ROOT}', flush=True)
    print(f'PYTHON: {sys.executable}', flush=True)
    print('DATA: Historical only; no live feeds', flush=True)
    if dry_run:
        print('DRY_RUN: No AI execution, database writes, or report generation.', flush=True)
        print(f'WOULD_RUN: {sys.executable} {RUNNER}', flush=True)
        print('THEN: Generate reports only for this run if COMPLETED_VALIDATED.', flush=True)
        return 0

    # Capture output to obtain the exact run ID. Forward it after execution.
    # The existing runner maintains its exclusive lock and SQLite tracking.
    completed = subprocess.run([sys.executable, str(RUNNER)], cwd=str(ROOT),
                               text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, check=False)
    print(completed.stdout, end='' if completed.stdout.endswith('\n') else '\n', flush=True)
    if completed.returncode != 0:
        print(f'SCHEDULED_JOB: RUNNER_NOT_VALIDATED (exit={completed.returncode}); no report generated.', flush=True)
        return completed.returncode

    match = UUID_PATTERN.search(completed.stdout)
    if not match:
        print('ERROR: Runner succeeded but run ID could not be extracted; no report generated.', flush=True)
        return 5
    run_id = match.group(1)
    try:
        with sqlite3.connect(f'file:{DATABASE}?mode=ro', uri=True, timeout=10) as con:
            row = con.execute('SELECT status, validation_status FROM automation_runs WHERE run_id=?',
                              (run_id,)).fetchone()
    except sqlite3.Error as exc:
        print(f'ERROR: Could not verify SQLite execution: {exc}', flush=True)
        return 5
    if row != ('COMPLETED_VALIDATED', 'pass'):
        print(f'ERROR: SQLite validation gate rejected report: {row!r}', flush=True)
        return 5

    report = subprocess.run([sys.executable, str(REPORTER), '--run-id', run_id],
                            cwd=str(ROOT), text=True, capture_output=True, check=False)
    if report.stdout:
        print(report.stdout, end='' if report.stdout.endswith('\n') else '\n', flush=True)
    if report.stderr:
        print(report.stderr, file=sys.stderr, flush=True)
    if report.returncode != 0:
        print(f'SCHEDULED_JOB: REPORT_FAILED (exit={report.returncode})', flush=True)
        return 6
    print(f'SCHEDULED_JOB: COMPLETED_WITH_REPORTS | run_id={run_id}', flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Manually test scheduling workflow before enabling launchd')
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--dry-run', action='store_true', help='Check paths; do not run AI')
    actions.add_argument('--run', action='store_true', help='Run AI once and report if validated')
    args = parser.parse_args()
    return execute(dry_run=args.dry_run)


if __name__ == '__main__':
    raise SystemExit(main())
