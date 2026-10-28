
import pandas as pd

from forecast_request import (
    create_forecast_request,
    validate_historical_cutoff,
    print_forecast_request,
)


print("\nINNEVA.E — Forecast Architecture Tests")

issue_time = "2026-10-01T00:00:00+00:00"

expected_hours = {
    "1h": 1,
    "24h": 24,
    "7d": 168,
    "30d": 720,
}

for horizon, expected in expected_hours.items():
    request = create_forecast_request(
        issue_time=issue_time,
        horizon=horizon,
    )

    assert request.horizon_hours == expected

    assert (
        request.forecast_end_utc
        - request.forecast_start_utc
    ) == pd.Timedelta(hours=expected)

    print(f"PASS — {horizon}: {expected} hours")


# Valid historical observations
historical = pd.DataFrame({
    "hour_start_utc": [
        "2026-09-30T21:00:00+00:00",
        "2026-09-30T22:00:00+00:00",
        "2026-09-30T23:00:00+00:00",
    ],
    "actual_load_mw": [
        11000,
        10800,
        10500,
    ],
})

request = create_forecast_request(
    issue_time=issue_time,
    horizon="24h",
)

assert validate_historical_cutoff(
    historical,
    request,
)

print("PASS — Historical cutoff validation")


# Future observation should be rejected
invalid_historical = pd.concat(
    [
        historical,
        pd.DataFrame({
            "hour_start_utc": [
                "2026-10-01T00:00:00+00:00"
            ],
            "actual_load_mw": [10300],
        }),
    ],
    ignore_index=True,
)

try:
    validate_historical_cutoff(
        invalid_historical,
        request,
    )
except ValueError:
    print("PASS — Future observations rejected")
else:
    raise AssertionError(
        "Future observation was not rejected."
    )


# Naive timestamps should be rejected
try:
    create_forecast_request(
        "2026-10-01 00:00:00",
        "1h",
    )
except ValueError:
    print("PASS — Timezone validation")
else:
    raise AssertionError(
        "Naive timestamp was not rejected."
    )


# Unsupported horizon should be rejected
try:
    create_forecast_request(
        issue_time,
        "48h",
    )
except ValueError:
    print("PASS — Unsupported horizon rejected")
else:
    raise AssertionError(
        "Unsupported horizon was not rejected."
    )


print_forecast_request(request)

print("\nALL FORECAST ARCHITECTURE TESTS PASSED")
