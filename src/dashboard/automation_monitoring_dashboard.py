"""INNEVA.E 19.5: read-only Streamlit automation monitoring page."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / 'reports' / 'automation' / 'automation.sqlite3'
REPORTS = ROOT / 'reports' / 'automation' / 'generated_reports'


def _read_history():
    if not DB.is_file():
        return [], {}
    # Read-only URI: the dashboard must not initialize or change the database.
    with sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True, timeout=5) as con:
        con.row_factory = sqlite3.Row
        runs = [dict(r) for r in con.execute('''
            SELECT run_id, job_id, started_at_utc, finished_at_utc, status,
                   dataset_mode, model, duration_seconds, validation_status,
                   error_type, error_message, question, validation_json,
                   result_json, historical_data_only
            FROM automation_runs ORDER BY started_at_utc DESC, run_id DESC LIMIT 500
        ''')]
        ids = [r['run_id'] for r in runs]
        tools = {run_id: [] for run_id in ids}
        if ids:
            placeholders = ','.join('?' for _ in ids)
            for row in con.execute(f'''SELECT run_id, tool_name FROM automation_run_tools
                WHERE run_id IN ({placeholders}) ORDER BY run_id, tool_order''', ids):
                tools[row['run_id']].append(row['tool_name'])
        return runs, tools


def _json_object(raw):
    try:
        value = json.loads(raw) if raw else None
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def render_automation_monitoring_dashboard():
    st.header('Automation Monitoring')
    st.caption('Checkpoint 19.5 · Read-only SQLite execution history · Historical data only')
    st.info('This page monitors locally executed jobs. It does not schedule or start analyses. '
            'The displayed records are historical, not live energy observations.')
    if st.button('Refresh execution history', key='automation_refresh'):
        st.rerun()
    try:
        runs, tools = _read_history()
    except (sqlite3.Error, OSError) as exc:
        st.error(f'Unable to read automation history: {type(exc).__name__}: {exc}')
        return
    if not runs:
        st.warning('No automation executions found. Run the automation runner from Terminal first.')
        st.code('python3 src/automation/automation_runner.py', language='bash')
        return

    completed = sum(r['status'] == 'COMPLETED_VALIDATED' for r in runs)
    failed = sum(r['status'] in ('FAILED_EXECUTION', 'FAILED_VALIDATION', 'INTERRUPTED') for r in runs)
    durations = [float(r['duration_seconds']) for r in runs if r['duration_seconds'] is not None]
    a, b, c, d = st.columns(4)
    a.metric('Recorded runs (latest 500)', len(runs))
    b.metric('Validated', completed)
    c.metric('Failed / interrupted', failed)
    d.metric('Mean duration', f'{sum(durations)/len(durations):.1f} s' if durations else 'N/A')
    st.caption('Metrics cover up to the 500 most recent executions, not necessarily all database history.')

    statuses = sorted({r['status'] for r in runs})
    filter_status = st.selectbox('Filter by status', ['All'] + statuses, key='automation_status_filter')
    filtered = [r for r in runs if filter_status == 'All' or r['status'] == filter_status]
    st.subheader('Execution history')
    if filtered:
        st.dataframe(pd.DataFrame([{
            'Started (UTC)': r['started_at_utc'],
            'Status': r['status'],
            'Dataset': r['dataset_mode'],
            'Duration (s)': r['duration_seconds'],
            'Validation': r['validation_status'],
            'Tools': ', '.join(tools.get(r['run_id'], [])),
            'Run ID': r['run_id'],
        } for r in filtered]), use_container_width=True, hide_index=True)
    else:
        st.caption('No runs match the selected filter.')
        return

    selected = st.selectbox('Inspect execution', filtered,
                            format_func=lambda r: f"{r['started_at_utc']} | {r['status']} | {r['run_id'][:8]}",
                            key='automation_selected_run')
    st.write('**Question:**', selected['question'])
    st.write('**Run ID:**', selected['run_id'])
    st.write('**Model / dataset:**', selected['model'], '/', selected['dataset_mode'])
    st.write('**Executed tools:**', tools.get(selected['run_id'], []))
    if selected['error_type'] or selected['error_message']:
        st.error(f"{selected['error_type'] or 'Error'}: {selected['error_message'] or 'No details recorded'}")
    validation = _json_object(selected['validation_json'])
    with st.expander('Validation evidence'):
        st.write('Validation status:', validation.get('status', 'Unavailable'))
        checks = validation.get('checks') or {}
        if isinstance(checks, dict) and checks:
            st.dataframe(pd.DataFrame([{'Check': k, 'Passed': bool(v)} for k, v in checks.items()]),
                         use_container_width=True, hide_index=True)
        if validation.get('errors'):
            st.write('Errors:', validation['errors'])
        if validation.get('warning'):
            st.caption(str(validation['warning']))
    with st.expander('Stored execution evidence'):
        evidence = _json_object(selected['result_json'])
        if evidence:
            st.json(evidence)
        else:
            st.caption('No stored result evidence.')

    st.subheader('Generated reports')
    # Restrict filenames to the exact selected UUID, never accept user-provided paths.
    run_id = selected['run_id']
    validated = (selected['status'] == 'COMPLETED_VALIDATED'
                 and selected['validation_status'] == 'pass'
                 and bool(selected['historical_data_only']))
    if not validated:
        st.warning('Reports are available only for validated historical executions.')
        return
    for extension, mime in [('md', 'text/markdown'), ('pdf', 'application/pdf')]:
        path = REPORTS / f'energy_report_{run_id}.{extension}'
        if path.is_file():
            st.download_button(f'Download {extension.upper()} report', data=path.read_bytes(),
                               file_name=path.name, mime=mime,
                               key=f'automation_report_{extension}_{run_id}')
        else:
            st.caption(f'{extension.upper()} report not generated for this run.')
    st.caption('To generate a missing report, run:')
    st.code(f'python3 src/automation/report_generator.py --run-id {run_id}', language='bash')


if __name__ == '__main__':
    st.set_page_config(page_title='INNEVA.E | Automation Monitoring', page_icon='⚡', layout='wide')
    render_automation_monitoring_dashboard()
