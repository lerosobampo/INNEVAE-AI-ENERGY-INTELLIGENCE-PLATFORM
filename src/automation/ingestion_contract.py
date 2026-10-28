
"""INNEVA.E checkpoint 20.1: read-only incremental ingestion contract validator.

Does not modify the canonical CSV or any project database.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FORECASTING_DIR = ROOT / 'src' / 'forecasting'

if str(FORECASTING_DIR) not in sys.path:
    sys.path.insert(0, str(FORECASTING_DIR))

from unified_data_loader import EXPECTED_COLUMNS, load_energy_history

TIME = 'hour_start_utc'

FLAGS = {
    'actual_load_missing': ['actual_load_mw', 'actual_load_mwh'],
    'solar_missing': ['solar_mw', 'solar_mwh'],
    'wind_onshore_missing': ['wind_onshore_mw', 'wind_onshore_mwh'],
    'wind_offshore_missing': ['wind_offshore_mw', 'wind_offshore_mwh'],
    'price_missing': ['wholesale_price_eur_mwh'],
}


def validate_candidate(candidate_path: Path, canonical_path: Path) -> dict:
    if not candidate_path.is_file():
        raise FileNotFoundError(
            f'Candidate CSV not found: {candidate_path}'
        )

    current = load_energy_history(
        mode='full_history',
        path=canonical_path,
    )

    incoming = pd.read_csv(candidate_path)

    if list(incoming.columns) != list(EXPECTED_COLUMNS):
        raise ValueError(
            'Candidate must have exactly the canonical 37 columns '
            'in their original order'
        )

    if incoming.empty:
        raise ValueError('Candidate CSV has no observations')

    for col in ('hour_start_utc', 'hour_end_utc'):
        incoming[col] = pd.to_datetime(
            incoming[col],
            utc=True,
            errors='raise',
            format='mixed',
        )

        if incoming[col].isna().any():
            raise ValueError(f'Null timestamp: {col}')

    if incoming[TIME].duplicated().any():
        raise ValueError('Duplicate candidate timestamps')

    if not incoming[TIME].is_monotonic_increasing:
        raise ValueError(
            'Candidate timestamps must be strictly ascending'
        )

    if not (
        incoming['hour_end_utc'] - incoming[TIME]
        == pd.Timedelta(hours=1)
    ).all():
        raise ValueError(
            'Each observation must represent exactly one UTC hour'
        )

    expected_first = (
        current[TIME].max() + pd.Timedelta(hours=1)
    )

    if incoming[TIME].iloc[0] != expected_first:
        raise ValueError(
            f'Expected first new UTC hour {expected_first}; '
            f'received {incoming[TIME].iloc[0]} (overlap or gap)'
        )

    expected = pd.date_range(
        expected_first,
        periods=len(incoming),
        freq='h',
    )

    if not incoming[TIME].reset_index(drop=True).equals(
        pd.Series(expected, name=TIME)
    ):
        raise ValueError(
            'Candidate has a gap or irregular hourly timestamps'
        )

    for flag, measurements in FLAGS.items():
        if incoming[flag].isna().any():
            raise ValueError(
                f'Null missingness flag: {flag}'
            )

        # CSV parser must infer a true boolean,
        # not arbitrary strings.
        if not pd.api.types.is_bool_dtype(incoming[flag]):
            raise ValueError(
                f'Flag must contain true/false booleans: {flag}'
            )

        for measurement in measurements:
            if not incoming[measurement].isna().equals(
                incoming[flag]
            ):
                raise ValueError(
                    f'Missingness flag mismatch: '
                    f'{flag} versus {measurement}'
                )

    if not (
        incoming['hour_of_day'] == incoming[TIME].dt.hour
    ).all():
        raise ValueError(
            'hour_of_day disagrees with UTC timestamp'
        )

    if not (
        incoming['day_of_week'] == incoming[TIME].dt.day_of_week
    ).all():
        raise ValueError(
            'day_of_week disagrees with UTC timestamp'
        )

    if not (
        incoming['month'] == incoming[TIME].dt.month
    ).all():
        raise ValueError(
            'month disagrees with UTC timestamp'
        )

    if not (
        incoming['is_weekend']
        == (incoming[TIME].dt.day_of_week >= 5)
    ).all():
        raise ValueError(
            'is_weekend disagrees with UTC timestamp'
        )

    return {
        'status': 'VALIDATED_STAGING_ONLY',
        'canonical_rows': len(current),
        'candidate_rows': len(incoming),
        'first_new_hour_utc': incoming[TIME].iloc[0].isoformat(),
        'last_new_hour_utc': incoming[TIME].iloc[-1].isoformat(),
        'new_missing_offshore_hours': int(
            incoming['wind_offshore_mw'].isna().sum()
        ),
        'new_missing_price_hours': int(
            incoming['wholesale_price_eur_mwh'].isna().sum()
        ),
        'canonical_unchanged': True,
    }


def main():
    parser = argparse.ArgumentParser(
        description='Read-only INNEVA.E staging contract validator'
    )

    parser.add_argument(
        '--candidate',
        type=Path,
        required=True,
    )

    parser.add_argument(
        '--canonical',
        type=Path,
        default=(
            ROOT
            / 'data/forecasting/energy_intelligence_hourly.csv'
        ),
    )

    args = parser.parse_args()

    try:
        result = validate_candidate(
            args.candidate,
            args.canonical,
        )

        print(json.dumps(result, indent=2))
        return 0

    except (
        ValueError,
        FileNotFoundError,
        pd.errors.ParserError,
    ) as exc:
        print(
            f'STAGING_REJECTED: {exc}',
            file=sys.stderr,
        )
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
