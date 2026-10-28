"""INNEVA.E 19.4 — generate factual Markdown/PDF reports from validated SQLite runs.

Install: src/automation/report_generator.py
Requires: reportlab (pip install reportlab). Does not call Ollama.
"""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / 'reports' / 'automation' / 'automation.sqlite3'
OUTPUT = ROOT / 'reports' / 'automation' / 'generated_reports'
UUID_RE = re.compile(r'^[0-9a-fA-F-]{36}$')


def load_validated_run(run_id=None):
    if not DB.is_file():
        raise FileNotFoundError(f'SQLite history not found: {DB}')
    with sqlite3.connect(f'file:{DB}?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        if run_id:
            row = conn.execute('SELECT * FROM automation_runs WHERE run_id=?', (run_id,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM automation_runs WHERE status='COMPLETED_VALIDATED' ORDER BY started_at_utc DESC, run_id DESC LIMIT 1").fetchone()
        if row is None:
            raise ValueError('No matching execution found.')
        r = dict(row)
        if r['status'] != 'COMPLETED_VALIDATED' or r['validation_status'] != 'pass':
            raise ValueError('Report blocked: run is not COMPLETED_VALIDATED with passing stored validation.')
        if not r['historical_data_only']:
            raise ValueError('Report blocked: run is not marked historical-data-only.')
        try:
            result = json.loads(r['result_json'])
            validation = json.loads(r['validation_json'])
        except (TypeError, ValueError) as exc:
            raise ValueError('Report blocked: missing or malformed evidence JSON.') from exc
        if not isinstance(result, dict) or not isinstance(validation, dict):
            raise ValueError('Report blocked: malformed evidence objects.')
        if result.get('status') != 'completed' or result.get('validation', {}).get('status') != 'pass' or validation.get('status') != 'pass':
            raise ValueError('Report blocked: persisted agent evidence does not confirm validation.')
        if result.get('dataset_mode') != r['dataset_mode']:
            raise ValueError('Report blocked: dataset mode mismatch.')
        tools = conn.execute('SELECT tool_name FROM automation_run_tools WHERE run_id=? ORDER BY tool_order', (r['run_id'],)).fetchall()
        names = [t['tool_name'] for t in tools]
        if names != (result.get('selected_tools') or []):
            raise ValueError('Report blocked: stored tool list differs from agent evidence.')
        evidence = result.get('tool_results')
        if not isinstance(evidence, dict):
            raise ValueError('Report blocked: tool evidence missing.')
        for name in names:
            if name not in evidence or not isinstance(evidence[name], dict):
                raise ValueError(f'Report blocked: missing evidence for {name}.')
        return r, result, validation, names


def number(value, decimals=2):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 'Not available'
    return f'{value:,.{decimals}f}'


def scalar(value):
    return 'Not available' if value is None else str(value)


def make_sections(r, result, validation, tools):
    evidence = result['tool_results']
    overview = evidence.get('get_energy_overview') or {}
    quality = evidence.get('get_data_quality') or {}
    forecast = evidence.get('forecast_next_hour') or {}
    sections = []
    def section(title, lines):
        sections.append((title, lines))
    section('Executive summary', [
        'This report describes a validated automated analysis of a historical energy dataset. It is not live operational intelligence.',
        f"Dataset: {r['dataset_mode']}. Executed tools: {', '.join(tools) or 'none'}.",
        'Findings below are transcribed from the persisted tool evidence, not inferred from the AI narrative.'
    ])
    if overview:
        section('Historical energy overview', [
            f"Coverage: {scalar(overview.get('first_timestamp_utc'))} to {scalar(overview.get('last_timestamp_utc'))} (UTC timestamps).",
            f"Observations: {scalar(overview.get('observation_count'))}.",
            f"Average electricity demand: {number(overview.get('average_demand_mw'))} MW.",
            f"Peak electricity demand: {number(overview.get('peak_demand_mw'))} MW.",
            f"Average renewable generation: {number(overview.get('average_renewable_generation_mw'))} MW.",
            f"Average observed wholesale price: {number(overview.get('average_wholesale_price_eur_mwh'))} EUR/MWh.",
            scalar(overview.get('price_data_note')),
        ])
    if quality:
        missing = quality.get('missing_by_variable') or {}
        details = [f'{key}: {value} missing observation(s).' for key, value in missing.items() if isinstance(value, int) and value > 0]
        section('Data quality', [
            f"Tool status: {scalar(quality.get('status'))}.",
            f"Total hours: {scalar(quality.get('total_hours'))}; unique hours: {scalar(quality.get('unique_hours'))}.",
            *(details or ['No positive missing-value counts reported in the stored tool evidence.']),
            f"Price imputation count: {scalar(quality.get('imputed_price_count'))}.",
            scalar(quality.get('data_quality_note')),
        ])
    if forecast:
        section('Historical one-hour forecast', [
            f"Method: {scalar(forecast.get('model'))}.",
            f"Last observed timestamp: {scalar(forecast.get('latest_observation_utc'))}.",
            f"Forecast target timestamp: {scalar(forecast.get('forecast_timestamp_utc'))}.",
            f"Predicted electricity demand: {number(forecast.get('predicted_demand_mw'))} MW.",
            f"Forecast generation timestamp: {scalar(forecast.get('generated_at_utc'))}.",
            'This is a historical persistence scenario, NOT a live forecast. The target timestamp is distinct from report generation time.',
        ])
    section('Execution and validation', [
        f"Run ID: {r['run_id']}.", f"Job ID: {r['job_id']}.",
        f"Started (UTC): {r['started_at_utc']}.", f"Finished (UTC): {scalar(r['finished_at_utc'])}.",
        f"Duration: {number(r['duration_seconds'], 3)} seconds.",
        f"Model: {r['model']}.", f"Run status: {r['status']}.",
        f"Validation: {validation['status']}; {len(validation.get('checks') or {})} configured checks recorded.",
        'Automated validation does not guarantee underlying data accuracy.',
    ])
    section('Limitations and provenance', [
        'Source: local INNEVA.E SQLite automation history and its stored analytical tool results.',
        'The data is historical; no live feed, live demand prediction, or real-time market claim is made.',
        'Missing observations are not assumed to be imputed. Check individual tool evidence for completeness.',
        'This document is a report of one stored execution, not an independently audited energy dataset.',
    ])
    return sections


def render_markdown(r, sections):
    lines = ['# INNEVA.E | Historical Energy Intelligence Report', '',
             f"**Run ID:** `{r['run_id']}`  ", f"**Dataset:** `{r['dataset_mode']}`  ",
             '**Classification:** Historical analysis — not live forecasting', '']
    for title, entries in sections:
        lines += [f'## {title}', '']
        lines += [f'- {entry}' for entry in entries]
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def render_pdf(path, r, sections):
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
    except ImportError as exc:
        raise RuntimeError('PDF generation requires reportlab: python3 -m pip install reportlab') from exc
    doc = SimpleDocTemplate(str(path), pagesize=(595.28, 841.89), rightMargin=49, leftMargin=49, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ReportTitleX', parent=styles['Title'], fontSize=17, leading=22, textColor=colors.HexColor('#16334C'), spaceAfter=13))
    styles.add(ParagraphStyle(name='ReportHeadX', parent=styles['Heading2'], fontSize=11.5, leading=15, textColor=colors.HexColor('#16657B'), spaceBefore=13, spaceAfter=6))
    styles.add(ParagraphStyle(name='ReportBodyX', parent=styles['BodyText'], fontSize=9, leading=13, spaceAfter=5))
    styles.add(ParagraphStyle(name='ReportNoteX', parent=styles['BodyText'], fontSize=9, leading=13, textColor=colors.HexColor('#555E68')))
    story = [Paragraph('INNEVA.E | Historical Energy Intelligence Report', styles['ReportTitleX']),
             Paragraph(f"Run: {escape(r['run_id'])} | Dataset: {escape(r['dataset_mode'])}", styles['ReportNoteX']),
             Paragraph('<b>HISTORICAL DATA ONLY — NOT A LIVE FORECAST</b>', styles['ReportNoteX']), Spacer(1, 8)]
    for title, entries in sections:
        story.append(Paragraph(escape(title), styles['ReportHeadX']))
        for entry in entries:
            story.append(Paragraph('&#8226; ' + escape(entry), styles['ReportBodyX']))
    def footer(canvas, document):
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#6A7480'))
        canvas.drawString(49, 31, 'INNEVA.E | Historical analysis only')
        canvas.drawRightString(546, 31, f'Page {document.page}')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def generate(run_id=None):
    r, result, validation, tools = load_validated_run(run_id)
    sections = make_sections(r, result, validation, tools)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    # The ID comes from SQLite, not user-supplied file paths.
    if not UUID_RE.fullmatch(r['run_id']):
        raise ValueError('Unsafe run ID in database; refusing to create report filename.')
    base = OUTPUT / f"energy_report_{r['run_id']}"
    md_path = base.with_suffix('.md')
    pdf_path = base.with_suffix('.pdf')
    # Prepare PDF before publishing the Markdown so a missing dependency cannot leave a partial pair.
    tmp_pdf = OUTPUT / f'.{base.name}.tmp.pdf'
    try:
        render_pdf(tmp_pdf, r, sections)
        md_path.write_text(render_markdown(r, sections), encoding='utf-8')
        tmp_pdf.replace(pdf_path)
    finally:
        tmp_pdf.unlink(missing_ok=True)
    return md_path, pdf_path


def main():
    parser = argparse.ArgumentParser(description='Generate Markdown and PDF from validated SQLite automation evidence (no Ollama).')
    parser.add_argument('--run-id', help='Exact execution UUID (default: most recent validated run)')
    args = parser.parse_args()
    try:
        md, pdf = generate(args.run_id)
    except (ValueError, FileNotFoundError, RuntimeError, sqlite3.Error, OSError) as exc:
        print(f'REPORT_BLOCKED: {exc}', file=sys.stderr)
        return 2
    print('STATUS: REPORT_GENERATED')
    print(f'MARKDOWN: {md}')
    print(f'PDF: {pdf}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
