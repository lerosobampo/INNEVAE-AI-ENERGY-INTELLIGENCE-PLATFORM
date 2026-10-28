
from dataclasses import dataclass
from datetime import timedelta

import pandas as pd


SUPPORTED_HORIZONS = {
    "1h": 1,
    "24h": 24,
    "7d": 168,
    "30d": 720,
}


@dataclass(frozen=True)
class ForecastRequest:
    issue_time_utc: pd.Timestamp
    horizon: str
    horizon_hours: int
    forecast_start_utc: pd.Timestamp
    forecast_end_utc: pd.Timestamp


def create_forecast_request(
    issue_time,
    horizon="24h",
):
    """
    Create and validate a forecasting request.

    The issue time is the boundary at which the forecast
    is generated. The first predicted hour starts at
    issue_time.

    All historical inputs must be available strictly
    before the issue time.
    """

    if horizon not in SUPPORTED_HORIZONS:
        raise ValueError(
            f"Unsupported horizon: {horizon}. "
            f"Choose from {list(SUPPORTED_HORIZONS)}"
        )

    timestamp = pd.Timestamp(issue_time)

    if pd.isna(timestamp):
        raise ValueError("Issue time cannot be missing.")

    if timestamp.tzinfo is None:
        raise ValueError(
            "Issue time must include a timezone. "
            "Use UTC or an explicit timezone offset."
        )

    timestamp = timestamp.tz_convert("UTC")

    if (
        timestamp.minute != 0
        or timestamp.second != 0
        or timestamp.microsecond != 0
        or timestamp.nanosecond != 0
    ):
        raise ValueError(
            "Issue time must align with the start of an hour."
        )

    hours = SUPPORTED_HORIZONS[horizon]

    forecast_end = timestamp + timedelta(hours=hours)

    return ForecastRequest(
        issue_time_utc=timestamp,
        horizon=horizon,
        horizon_hours=hours,
        forecast_start_utc=timestamp,
        forecast_end_utc=forecast_end,
    )


def validate_historical_cutoff(
    historical_data,
    request,
    timestamp_column="hour_start_utc",
):
    """
    Ensure no historical observation starts at or
    after the forecast issue time.

    This checks timestamp boundaries only.
    It does not establish publication availability.
    """

    if timestamp_column not in historical_data.columns:
        raise ValueError(
            f"Missing timestamp column: {timestamp_column}"
        )

    timestamps = pd.to_datetime(
        historical_data[timestamp_column],
        utc=True,
        errors="raise",
    )

    if timestamps.isna().any():
        raise ValueError(
            "Historical data contains missing timestamps."
        )

    if timestamps.empty:
        raise ValueError(
            "Historical data cannot be empty."
        )

    latest_timestamp = timestamps.max()

    if latest_timestamp >= request.issue_time_utc:
        raise ValueError(
            "Historical data contains observations "
            "at or after the forecast issue time."
        )

    return True


def print_forecast_request(request):
    print("\nINNEVA.E — Forecast Request")

    print(
        f"Issue time: {request.issue_time_utc}"
    )

    print(
        f"Horizon: {request.horizon}"
    )

    print(
        f"Forecast hours: {request.horizon_hours}"
    )

    print(
        f"Forecast starts: {request.forecast_start_utc}"
    )

    print(
        f"Forecast ends (exclusive): "
        f"{request.forecast_end_utc}"
    )
