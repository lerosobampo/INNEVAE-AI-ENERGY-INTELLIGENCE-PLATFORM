
"""INNEVA.E shared historical energy data loader (Checkpoint 17.8B).

Uses the canonical 37-column historical CSV without renaming its variables.
Read-only: no modifications to datasets, models or databases.
"""
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_PATH = (
    PROJECT_ROOT
    / 'data'
    / 'forecasting'
    / 'energy_intelligence_hourly.csv'
)

TIME_COLUMN = 'hour_start_utc'

EXPECTED_COLUMNS = (
    'hour_start_utc',
    'hour_end_utc',
    'actual_load_mw',
    'actual_load_mwh',
    'actual_load_missing',
    'solar_mw',
    'solar_mwh',
    'solar_missing',
    'wind_onshore_mw',
    'wind_onshore_mwh',
    'wind_onshore_missing',
    'wind_offshore_mw',
    'wind_offshore_mwh',
    'wind_offshore_missing',
    'wholesale_price_eur_mwh',
    'price_missing',
    'station_count',
    'temperature_c',
    'wind_speed_ms',
    'solar_radiation_wm2',
    'cloud_cover_oktas',
    'relative_humidity_pct',
    'precipitation_mm',
    'sunshine_hours',
    'pressure_hpa',
    'temperature_c_station_count',
    'wind_speed_ms_station_count',
    'solar_radiation_wm2_station_count',
    'cloud_cover_oktas_station_count',
    'relative_humidity_pct_station_count',
    'precipitation_mm_station_count',
    'sunshine_hours_station_count',
    'pressure_hpa_station_count',
    'hour_of_day',
    'day_of_week',
    'month',
    'is_weekend',
)


def load_energy_history(mode='development_90d', path=None):
    """Return canonical energy records for the requested period.

    mode='development_90d': latest 90 complete UTC calendar days.
    mode='full_history': all available hourly observations.
    """
    if mode not in {
        'development_90d',
        'full_history',
    }:
        raise ValueError(
            'mode must be development_90d or full_history'
        )

    csv_path = (
        Path(path)
        if path is not None
        else DATA_PATH
    )

    if not csv_path.is_file():
        raise FileNotFoundError(
            f'Historical dataset not found: {csv_path}'
        )

    df = pd.read_csv(csv_path)

    missing_columns = sorted(
        set(EXPECTED_COLUMNS) - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            f'Historical dataset missing columns: '
            f'{missing_columns}'
        )

    if list(df.columns) != list(EXPECTED_COLUMNS):
        raise ValueError(
            'Canonical CSV column order/schema differs '
            'from the expected 37 columns.'
        )

    # Supports both historical timestamp strings
    # and ISO 8601 timestamp strings in the same CSV.
    # Invalid timestamps are still rejected.
    for col in (
        'hour_start_utc',
        'hour_end_utc',
    ):
        df[col] = pd.to_datetime(
            df[col],
            utc=True,
            errors='raise',
            format='mixed',
        )

    if df[TIME_COLUMN].isna().any():
        raise ValueError(
            'Historical dataset contains null start timestamps.'
        )

    df = (
        df.sort_values(TIME_COLUMN)
        .reset_index(drop=True)
    )

    if df[TIME_COLUMN].duplicated().any():
        raise ValueError(
            'Historical dataset contains duplicate hourly timestamps.'
        )

    if not (
        df['hour_end_utc'] - df[TIME_COLUMN]
        == pd.Timedelta(hours=1)
    ).all():
        raise ValueError(
            'Expected each record to represent exactly one hour.'
        )

    if mode == 'development_90d':
        # A calendar day is complete only if the last
        # available timestamp is 23:00 UTC.
        # Otherwise end at the preceding UTC midnight.
        last_timestamp = df[TIME_COLUMN].max()

        last_day_start = last_timestamp.normalize()

        end_exclusive = (
            last_day_start + pd.Timedelta(days=1)
            if last_timestamp.hour == 23
            else last_day_start
        )

        start = (
            end_exclusive - pd.Timedelta(days=90)
        )

        df = df.loc[
            (df[TIME_COLUMN] >= start)
            & (df[TIME_COLUMN] < end_exclusive)
        ].copy()

        expected_rows = 90 * 24

        if len(df) != expected_rows:
            raise ValueError(
                f'90-day window has {len(df)} rows; '
                f'expected {expected_rows}.'
            )

    if df.empty:
        raise ValueError(
            'No historical observations found.'
        )

    expected_times = pd.date_range(
        start=df[TIME_COLUMN].iloc[0],
        end=df[TIME_COLUMN].iloc[-1],
        freq='h',
    )

    if (
        len(expected_times) != len(df)
        or not df[TIME_COLUMN]
        .reset_index(drop=True)
        .equals(
            pd.Series(
                expected_times,
                name=TIME_COLUMN,
            )
        )
    ):
        raise ValueError(
            'Selected dataset has missing or irregular '
            'hourly timestamps.'
        )

    return df.reset_index(drop=True)


def dataset_profile(df):
    """Summarize the selected dataset without modifying it."""
    return {
        'rows': len(df),
        'columns': len(df.columns),
        'first_hour_utc': str(
            df[TIME_COLUMN].min()
        ),
        'last_hour_utc': str(
            df[TIME_COLUMN].max()
        ),
        'missing_offshore_hours': int(
            df['wind_offshore_mw'].isna().sum()
        ),
        'missing_price_hours': int(
            df['wholesale_price_eur_mwh'].isna().sum()
        ),
    }


if __name__ == '__main__':
    for selected_mode in (
        'development_90d',
        'full_history',
    ):
        data = load_energy_history(selected_mode)

        print(f'\n{selected_mode}')

        for key, value in dataset_profile(data).items():
            print(f'  {key}: {value}')

    print(
        '\nUNIFIED DATA LOADER VALIDATION COMPLETE'
    )
