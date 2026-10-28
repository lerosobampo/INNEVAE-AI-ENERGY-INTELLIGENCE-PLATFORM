"""Deterministic verified facts from the canonical historical CSV tool results."""
from datetime import datetime, timezone

REQUIRED_TOOLS = ('get_energy_overview', 'get_data_quality', 'forecast_next_hour')


def format_utc(value):
    timestamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def build_verified_facts(tool_results):
    missing = set(REQUIRED_TOOLS) - set(tool_results)
    if missing:
        raise ValueError(f'Missing required tools: {sorted(missing)}')
    overview, quality, forecast = (tool_results[name] for name in REQUIRED_TOOLS)
    if overview.get('status') != 'success' or quality.get('status') not in ('pass', 'pass_with_warnings') or forecast.get('status') != 'success':
        raise ValueError('One or more analytical tools failed.')
    modes = [item.get('dataset_mode') for item in (overview, quality, forecast)]
    if not modes[0] or len(set(modes)) != 1:
        raise ValueError(f'Inconsistent dataset modes: {modes}')
    if overview['observation_count'] != quality['total_hours'] or overview['observation_count'] != forecast['observation_count']:
        raise ValueError('Inconsistent dataset observation counts.')
    if overview['last_timestamp_utc'] != forecast['latest_observation_utc']:
        raise ValueError('Forecast and overview use different latest observations.')
    if overview['originally_missing_prices'] != quality['originally_missing_prices']:
        raise ValueError('Price missingness counts disagree.')
    if overview['imputed_price_count'] != 0 or quality['imputed_price_count'] != 0:
        raise ValueError('Unexpected price imputation in canonical source.')
    if overview['renewable_complete_hours'] + quality['missing_offshore_wind'] != overview['observation_count']:
        raise ValueError('Renewable completeness does not match offshore missingness.')
    if quality['source_column_count'] != overview['source_column_count']:
        raise ValueError('Source column counts disagree.')
    price = overview['average_wholesale_price_eur_mwh']
    renewable = overview['average_renewable_generation_mw']
    price_label = f'EUR {price:,.2f}/MWh' if price is not None else 'Unavailable'
    renewable_label = f'{renewable:,.2f} MW' if renewable is not None else 'Unavailable'
    return f'''VERIFIED ENERGY INTELLIGENCE FACTS
==================================

DATASET
-------
Dataset mode: {modes[0]}
Historical hourly observations: {overview['observation_count']:,}
Original source columns: {overview['source_column_count']}
Period start: {format_utc(overview['first_timestamp_utc'])}
Period end: {format_utc(overview['last_timestamp_utc'])}
Data freshness: historical snapshot, not a live feed

MARKET OVERVIEW
---------------
Average electricity demand: {overview['average_demand_mw']:,.2f} MW
Peak electricity demand: {overview['peak_demand_mw']:,.2f} MW
Average total renewable generation (complete-component hours only): {renewable_label}
Hours with complete solar, onshore wind and offshore wind values: {overview['renewable_complete_hours']:,}
Average observed wholesale price (excluding missing observations): {price_label}
Hours with observed wholesale prices: {overview['observed_price_hours']:,}

DATA QUALITY
------------
Quality status: {quality['status']}
Missing demand values: {quality['missing_demand']}
Missing offshore wind values: {quality['missing_offshore_wind']}
Missing wholesale prices: {quality['originally_missing_prices']}
Missing analytical wholesale prices: {quality['remaining_missing_prices']}
Imputed wholesale prices: {quality['imputed_price_count']}
Price imputation method: none
Quality warnings: {'; '.join(quality['issues']) if quality['issues'] else 'none'}

DEMAND FORECAST
---------------
Forecast method: {forecast['model']}
Forecast horizon: {forecast['forecast_horizon_hours']} hour(s)
Latest historical observation: {format_utc(forecast['latest_observation_utc'])}
Historical forecast target: {format_utc(forecast['forecast_timestamp_utc'])}
Predicted demand: {forecast['predicted_demand_mw']:,.2f} MW

IMPORTANT LIMITATIONS
---------------------
- This is a historical dataset, not current electricity-market information.
- Missing wholesale prices are excluded from the average; no prices are imputed.
- Renewable averages exclude hours missing any generation component; missing offshore values are not zero.
- The one-hour persistence scenario carries forward the last observed demand; it does not use prices or weather.
- Completeness and timestamp checks do not establish source-data accuracy.'''


if __name__ == '__main__':
    from energy_tools import execute_tool
    print(build_verified_facts({name: execute_tool(name) for name in REQUIRED_TOOLS}))
