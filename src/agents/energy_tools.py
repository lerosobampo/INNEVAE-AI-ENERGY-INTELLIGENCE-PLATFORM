"""INNEVA.E AI tools backed by the canonical historical energy CSV.
Checkpoint 17.8D. Read-only; no September-only SQLite dependencies.
"""
import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for folder in (PROJECT_ROOT / 'src' / 'forecasting', PROJECT_ROOT / 'src' / 'ml'):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from unified_data_loader import load_energy_history
from demand_forecasting_tool import forecast_next_hour

DEFAULT_MODE = 'development_90d'


def _number(series):
    return pd.to_numeric(series, errors='coerce')


def _timestamp(value):
    return pd.Timestamp(value).isoformat()


def get_energy_overview(mode=DEFAULT_MODE):
    df = load_energy_history(mode)
    demand = _number(df['actual_load_mw'])
    solar = _number(df['solar_mw'])
    onshore = _number(df['wind_onshore_mw'])
    offshore = _number(df['wind_offshore_mw'])
    price = _number(df['wholesale_price_eur_mwh'])
    # min_count=3 prevents treating a missing renewable component as zero.
    renewable = pd.concat([solar, onshore, offshore], axis=1).sum(axis=1, min_count=3)
    if demand.notna().sum() == 0:
        raise ValueError('No valid demand observations.')
    return {
        'tool': 'get_energy_overview', 'status': 'success',
        'data_freshness': 'historical_snapshot', 'dataset_mode': mode,
        'observation_count': int(len(df)), 'source_column_count': int(len(df.columns)),
        'first_timestamp_utc': _timestamp(df['hour_start_utc'].iloc[0]),
        'last_timestamp_utc': _timestamp(df['hour_start_utc'].iloc[-1]),
        'average_demand_mw': round(float(demand.mean()), 2),
        'peak_demand_mw': round(float(demand.max()), 2),
        'average_renewable_generation_mw': round(float(renewable.mean()), 2) if renewable.notna().any() else None,
        'renewable_complete_hours': int(renewable.notna().sum()),
        'average_wholesale_price_eur_mwh': round(float(price.mean()), 2) if price.notna().any() else None,
        'observed_price_hours': int(price.notna().sum()),
        'originally_missing_prices': int(price.isna().sum()),
        'imputed_price_count': 0,
        'price_imputation_method': 'none',
        'price_data_note': 'Average uses observed wholesale prices only; missing values are excluded, not imputed.',
    }


def get_data_quality(mode=DEFAULT_MODE):
    df = load_energy_history(mode)
    numeric_columns = ('actual_load_mw', 'solar_mw', 'wind_onshore_mw', 'wind_offshore_mw',
                       'wholesale_price_eur_mwh', 'temperature_c', 'wind_speed_ms',
                       'solar_radiation_wm2', 'cloud_cover_oktas', 'relative_humidity_pct',
                       'precipitation_mm', 'sunshine_hours', 'pressure_hpa')
    missing = {name: int(_number(df[name]).isna().sum()) for name in numeric_columns}
    issues = [f'{count} missing values in {name}.' for name, count in missing.items() if count]
    for col in ('actual_load_mw', 'solar_mw', 'wind_onshore_mw', 'wind_offshore_mw'):
        negatives = int((_number(df[col]) < 0).sum())
        if negatives:
            issues.append(f'{negatives} negative observations in {col}.')
    flag_mismatches = {}
    for value_col, flag_col in (('actual_load_mw','actual_load_missing'),
                                ('solar_mw','solar_missing'),
                                ('wind_onshore_mw','wind_onshore_missing'),
                                ('wind_offshore_mw','wind_offshore_missing'),
                                ('wholesale_price_eur_mwh','price_missing')):
        flags = df[flag_col].astype(str).str.strip().str.lower().isin(('1', 'true', 'yes'))
        mismatches = int((flags != _number(df[value_col]).isna()).sum())
        flag_mismatches[flag_col] = mismatches
        if mismatches:
            issues.append(f'{mismatches} missing-value flag mismatches in {flag_col}.')
    return {
        'tool': 'get_data_quality', 'status': 'pass_with_warnings' if issues else 'pass',
        'dataset_mode': mode, 'data_freshness': 'historical_snapshot',
        'scope': 'hourly_continuity_and_basic_completeness_checks',
        'total_hours': int(len(df)),
        'unique_hours': int(df['hour_start_utc'].nunique()),
        'source_column_count': int(len(df.columns)),
        'missing_by_variable': missing,
        'flag_mismatches': flag_mismatches,
        'missing_demand': missing['actual_load_mw'],
        'missing_offshore_wind': missing['wind_offshore_mw'],
        'originally_missing_prices': missing['wholesale_price_eur_mwh'],
        'remaining_missing_prices': missing['wholesale_price_eur_mwh'],
        'imputed_price_count': 0,
        'imputation_method': 'none',
        'missing_wind_weather': missing['wind_speed_ms'],
        'issues': issues,
        'data_quality_note': 'No price imputation is performed. Completeness and continuity do not establish source accuracy.',
    }


TOOL_REGISTRY = {
    'get_energy_overview': get_energy_overview,
    'get_data_quality': get_data_quality,
    'forecast_next_hour': forecast_next_hour,
}
TOOL_DESCRIPTIONS = {
    'get_energy_overview': 'Summarize historical demand, complete renewable generation and observed wholesale prices.',
    'get_data_quality': 'Check canonical hourly continuity, missing values, and original missing-value flags.',
    'forecast_next_hour': 'Produce a historical one-hour persistence demand scenario using the canonical CSV.',
}


def execute_tool(tool_name, mode=DEFAULT_MODE):
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f'Unknown or unauthorized tool: {tool_name}')
    return TOOL_REGISTRY[tool_name](mode=mode)


if __name__ == '__main__':
    import json
    for name in TOOL_REGISTRY:
        print(f'\n{name}')
        print(json.dumps(execute_tool(name), indent=2))
