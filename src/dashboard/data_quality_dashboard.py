"""INNEVA.E Module 20.4 — read-only Streamlit quality-history dashboard."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
QUALITY_DB = ROOT / 'reports' / 'data_quality' / 'quality_history.sqlite3'
INGESTION_AUDIT = ROOT / 'reports' / 'automation' / 'ingestion_audit.jsonl'


def read_quality_history(db: Path = QUALITY_DB) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Open the existing database in read-only mode; never create or migrate it."""
    if not db.is_file():
        return pd.DataFrame(), pd.DataFrame()
    with sqlite3.connect(f'file:{db.resolve().as_posix()}?mode=ro', uri=True) as con:
        assessments = pd.read_sql_query(
            'SELECT assessment_id, assessed_at_utc, dataset_path, dataset_sha256, '
            'source_kind, status, rows, columns, first_hour_utc, last_hour_utc, '
            'fail_count, warning_count, report_json '
            'FROM quality_assessments ORDER BY assessed_at_utc DESC', con
        )
        issues = pd.read_sql_query(
            'SELECT assessment_id, issue_order, severity, check_name, affected_count, detail '
            'FROM quality_issues ORDER BY assessment_id, issue_order', con
        )
    return assessments, issues


def read_ingestion_events(path: Path = INGESTION_AUDIT) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    events = []
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict) and entry.get('event') in ('APPLY', 'ROLLBACK', 'INITIALIZE_DEVELOPMENT'):
                events.append(entry)
    return pd.DataFrame(events)


def render_data_quality_dashboard() -> None:
    st.header('Data Quality Monitoring')
    st.caption('Read-only quality history for historical and synthetic datasets. No live data feed is connected.')
    if st.button('Refresh quality history', key='refresh_quality_history'):
        st.rerun()
    try:
        history, issues = read_quality_history()
    except (sqlite3.Error, OSError, ValueError) as exc:
        st.error(f'Unable to read quality-history database: {exc}')
        return
    if history.empty:
        st.info('No saved quality assessments found. Run `python3 src/automation/data_quality_db.py record` first.')
        st.caption(f'Expected SQLite database: `{QUALITY_DB}`')
        return

    history = history.copy()
    history['assessed_at'] = pd.to_datetime(history['assessed_at_utc'], utc=True, errors='coerce')
    history['dataset_name'] = history['dataset_path'].map(lambda value: Path(str(value)).name)
    history = history.sort_values('assessed_at', ascending=False)

    options = sorted(history['dataset_path'].dropna().unique().tolist())
    selected_paths = st.multiselect('Datasets', options, default=options,
                                    format_func=lambda p: f'{Path(p).name} — {p}')
    selected_statuses = st.multiselect('Quality status', ['PASS', 'WARNING', 'FAIL'],
                                      default=['PASS', 'WARNING', 'FAIL'])
    filtered = history[history['dataset_path'].isin(selected_paths) & history['status'].isin(selected_statuses)].copy()
    if filtered.empty:
        st.info('No assessments match the selected filters.')
        return

    latest = filtered.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Latest status', str(latest['status']))
    c2.metric('Assessments shown', f'{len(filtered):,}')
    c3.metric('Latest failed checks', int(latest['fail_count']))
    c4.metric('Latest warnings', int(latest['warning_count']))
    st.caption(f"Latest selected assessment: {latest['assessed_at_utc']} | "
               f"Dataset: {latest['dataset_name']} | Source: {latest['source_kind']} | "
               f"Rows: {int(latest['rows']):,}")
    if latest['status'] == 'FAIL':
        st.error('The latest selected assessment failed quality validation.')
    elif latest['status'] == 'WARNING':
        st.warning('The latest selected assessment contains quality warnings.')
    else:
        st.success('The latest selected assessment passed its quality checks.')

    st.subheader('Assessment history')
    chart_data = filtered.sort_values('assessed_at').set_index('assessed_at')
    st.line_chart(chart_data[['fail_count', 'warning_count']])
    display_cols = ['assessed_at_utc', 'dataset_name', 'source_kind', 'status',
                    'rows', 'fail_count', 'warning_count', 'assessment_id']
    st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)
    st.download_button('Export selected assessment history (CSV)',
                       filtered[display_cols].to_csv(index=False).encode('utf-8'),
                       file_name='innevae_quality_history.csv', mime='text/csv')

    st.subheader('Assessment details')
    ids = filtered['assessment_id'].tolist()
    selected_id = st.selectbox('Select an assessment', ids,
        format_func=lambda aid: (
            f"{filtered.loc[filtered['assessment_id'] == aid, 'assessed_at_utc'].iloc[0]} — "
            f"{filtered.loc[filtered['assessment_id'] == aid, 'dataset_name'].iloc[0]} — {aid[:8]}"
        ))
    assessment = filtered.loc[filtered['assessment_id'] == selected_id].iloc[0]
    report = json.loads(assessment['report_json'])
    d1, d2, d3 = st.columns(3)
    d1.metric('Dataset rows', f"{int(assessment['rows']):,}")
    d2.metric('Failed checks', int(assessment['fail_count']))
    d3.metric('Warnings', int(assessment['warning_count']))
    st.write('First observation (UTC):', report.get('first_hour_utc'))
    st.write('Last observation (UTC):', report.get('last_hour_utc'))
    st.caption(f"SHA-256: `{assessment['dataset_sha256']}`")
    selected_issues = issues.loc[issues['assessment_id'] == selected_id].copy()
    if selected_issues.empty:
        st.success('No issues recorded for this assessment.')
    else:
        st.dataframe(selected_issues[['severity', 'check_name', 'affected_count', 'detail']],
                     use_container_width=True, hide_index=True)
    missing = report.get('missing_values', {})
    if missing:
        st.subheader('Missing observations in selected dataset')
        missing_df = pd.DataFrame([{'measurement': k, 'missing_rows': v} for k, v in missing.items()])
        st.bar_chart(missing_df.set_index('measurement'))
    else:
        st.caption('No missing values reported in this assessment.')
    with st.expander('Original quality report (JSON)'):
        st.json(report)

    st.subheader('Development ingestion activity')
    try:
        events = read_ingestion_events()
    except OSError as exc:
        st.warning(f'Unable to read ingestion audit: {exc}')
        return
    if events.empty:
        st.info('No development ingestion events found.')
    else:
        cols = [c for c in ['at_utc', 'event', 'run_id', 'previous_rows', 'appended_rows',
                            'new_rows', 'production_unchanged'] if c in events.columns]
        st.dataframe(events[cols].iloc[::-1].head(50), use_container_width=True, hide_index=True)
    st.caption('Assessments and ingestion events are historical records, not evidence of a live data pipeline.')
