"""INNEVA.E Checkpoint 19.3: validated local runner with SQLite + JSONL backup."""
from __future__ import annotations
import argparse
import contextlib
import fcntl
import io
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = PROJECT_ROOT / 'src' / 'agents'
AUTOMATION_DIR = PROJECT_ROOT / 'src' / 'automation'
LOG_DIR = PROJECT_ROOT / 'reports' / 'automation'
LOCK_FILE = LOG_DIR / '.automation_runner.lock'
RUN_LOG = LOG_DIR / 'runs.jsonl'
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))
from automation_db import DB_PATH, initialize, write_run, recover_interrupted

DEFAULT_QUESTION = ('Analyze average electricity demand, identify missing data, '
                    'and generate a one-hour-ahead historical forecast.')
MODES = ('development_90d', 'full_history')


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def save_record(record):
    """Append legacy JSONL snapshot while the exclusive lock is held."""
    with RUN_LOG.open('a', encoding='utf-8') as file:
        file.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')
        file.flush()
        os.fsync(file.fileno())


def run_once(question, mode, model):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    print(f'INNEVA.E AUTOMATION | run={run_id} | mode={mode} | model={model}', flush=True)
    with LOCK_FILE.open('a+') as lock_handle:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('SKIPPED_DUPLICATE: Another automation run holds the lock.', flush=True)
            return 3
        try:
            initialize()
            recovered = recover_interrupted()
            if recovered:
                print(f'RECOVERED: {recovered} previously interrupted run(s).', flush=True)
        except Exception as exc:
            print(f'DATABASE_ERROR: {type(exc).__name__}: {exc}', flush=True)
            return 4  # Never execute without durable tracking.
        record = {
            'run_id': run_id, 'job_id': 'historical_energy_manual',
            'started_at_utc': utc_now(), 'finished_at_utc': None,
            'status': 'RUNNING', 'question': question, 'dataset_mode': mode,
            'model': model, 'historical_data_only': True,
            'duration_seconds': None, 'selected_tools': [], 'validation': None,
            'agent_attempts': None, 'result': None, 'error_type': None, 'error_message': None,
        }
        started = time.monotonic()
        try:
            write_run(record)
        except Exception as exc:
            print(f'DATABASE_ERROR: Unable to record RUNNING state: {exc}', flush=True)
            return 4
        # Keep existing JSONL log, now as a secondary backup.
        try:
            save_record({k: v for k, v in record.items() if k != 'result'})
        except OSError as exc:
            print(f'JSONL_WARNING: {exc}', flush=True)
        captured = io.StringIO()
        try:
            if str(AGENT_DIR) not in sys.path:
                sys.path.insert(0, str(AGENT_DIR))
            from dynamic_energy_agent import run_dynamic_agent
            print('Running local historical analysis. This may take several minutes...', flush=True)
            with contextlib.redirect_stdout(captured):
                result = run_dynamic_agent(question, mode=mode, model=model)
            if not isinstance(result, dict):
                raise TypeError('Agent returned a non-dictionary result')
            record['selected_tools'] = result.get('selected_tools') or []
            record['validation'] = result.get('validation')
            record['agent_attempts'] = result.get('attempts')
            record['result'] = result
            validation = result.get('validation') or {}
            if result.get('status') == 'completed' and validation.get('status') == 'pass':
                record['status'] = 'COMPLETED_VALIDATED'
                exit_code = 0
            else:
                record['status'] = 'FAILED_VALIDATION' if result.get('status') == 'completed' else 'FAILED_EXECUTION'
                record['error_type'] = 'AgentResultRejected'
                record['error_message'] = (
                    f"Agent status={result.get('status')!r}; validation={validation.get('status')!r}")
                exit_code = 2
        except Exception as exc:
            record['status'] = 'FAILED_EXECUTION'
            record['error_type'] = type(exc).__name__
            record['error_message'] = str(exc)
            exit_code = 1
        finally:
            record['finished_at_utc'] = utc_now()
            record['duration_seconds'] = round(time.monotonic() - started, 3)
            try:
                write_run(record)
            except Exception as exc:
                print(f'DATABASE_ERROR: Final state could not be persisted: {exc}', flush=True)
                exit_code = 4
            try:
                save_record(record)
            except OSError as exc:
                print(f'JSONL_WARNING: {exc}', flush=True)
            print(f"STATUS: {record['status']}", flush=True)
            print(f"DURATION: {record['duration_seconds']:.1f}s", flush=True)
            print(f"TOOLS: {record['selected_tools']}", flush=True)
            if record['error_message']:
                print(f"ERROR: {record['error_type']}: {record['error_message']}", flush=True)
            if captured.getvalue():
                print('AGENT LOG:')
                print(captured.getvalue()[-4000:])
            print(f'SQLITE HISTORY: {DB_PATH}', flush=True)
            print(f'JSONL BACKUP: {RUN_LOG}', flush=True)
        return exit_code


def main():
    parser = argparse.ArgumentParser(description='INNEVA.E validated local AI automation')
    parser.add_argument('--question', default=DEFAULT_QUESTION)
    parser.add_argument('--mode', choices=MODES, default='development_90d')
    parser.add_argument('--model', default='qwen2.5:3b')
    args = parser.parse_args()
    if not args.question.strip():
        parser.error('--question cannot be empty')
    return run_once(args.question.strip(), args.mode, args.model)


if __name__ == '__main__':
    raise SystemExit(main())
