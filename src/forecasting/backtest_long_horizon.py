
from pathlib import Path
import time

import numpy as np
import pandas as pd

from one_hour_forecast import load_historical_data
from multi_hour_forecast import forecast_multiple_hours


PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/long_horizon_backtest"
)

HOLDOUT_START = pd.Timestamp(
    "2026-07-01T00:00:00+00:00"
)

HOLDOUT_END = pd.Timestamp(
    "2026-10-01T00:00:00+00:00"
)

EXPERIMENTS = {
    "7d": {
        "hours": 168,
        "frequency": "7D",
    },
    "30d": {
        "hours": 720,
        "frequency": "MS",
    },
}


def calculate_metrics(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    if len(actual) != len(predicted) or len(actual) == 0:
        raise ValueError("Invalid evaluation arrays.")

    if not (
        np.isfinite(actual).all()
        and np.isfinite(predicted).all()
    ):
        raise ValueError("Non-finite evaluation values.")

    errors = actual - predicted

    mae = np.mean(np.abs(errors))
    rmse = np.sqrt(np.mean(errors ** 2))

    nonzero = actual != 0

    mape = (
        np.mean(
            np.abs(errors[nonzero] / actual[nonzero])
        ) * 100
        if nonzero.any()
        else np.nan
    )

    return {
        "mae_mw": float(mae),
        "rmse_mw": float(rmse),
        "mape_pct": float(mape),
    }


def validate_historical_data(historical):
    timestamps = pd.DatetimeIndex(
        historical["hour_start_utc"]
    )

    if timestamps.has_duplicates:
        raise ValueError(
            "Duplicate historical timestamps."
        )

    expected = pd.date_range(
        start=timestamps.min(),
        end=timestamps.max(),
        freq="h",
    )

    if not timestamps.equals(expected):
        raise ValueError(
            "Historical timestamps are not continuous."
        )

    demand = pd.to_numeric(
        historical["actual_load_mw"],
        errors="coerce",
    )

    if not np.isfinite(demand.to_numpy()).all():
        raise ValueError(
            "Historical demand contains invalid values."
        )


def seasonal_naive_forecast(
    demand_lookup,
    issue_time,
    horizon_hours,
    season_hours,
):
    """
    Repeat the last fully observed seasonal pattern.

    For a 30-day forecast, the 24-hour baseline repeats
    the day before issue time 30 times.

    The 168-hour baseline repeats the last observed
    week as often as needed.

    No observations at or after issue time are used.
    """

    pattern_times = pd.date_range(
        start=issue_time - pd.Timedelta(
            hours=season_hours
        ),
        periods=season_hours,
        freq="h",
    )

    pattern = demand_lookup.reindex(
        pattern_times
    ).to_numpy(dtype=float)

    if not np.isfinite(pattern).all():
        raise ValueError(
            "Seasonal baseline history is incomplete."
        )

    indices = (
        np.arange(horizon_hours) % season_hours
    )

    return pattern[indices]


def generate_issue_times(horizon, config):
    if horizon == "7d":
        candidates = pd.date_range(
            start=HOLDOUT_START,
            end=HOLDOUT_END,
            freq=config["frequency"],
            inclusive="left",
        )

    elif horizon == "30d":
        candidates = pd.date_range(
            start=HOLDOUT_START,
            end=HOLDOUT_END,
            freq=config["frequency"],
            inclusive="left",
        )

    else:
        raise ValueError(
            f"Unsupported experiment: {horizon}"
        )

    valid = [
        timestamp
        for timestamp in candidates
        if timestamp + pd.Timedelta(
            hours=config["hours"]
        ) <= HOLDOUT_END
    ]

    return valid


def evaluate_horizon(
    historical,
    demand_lookup,
    horizon,
    config,
):
    horizon_hours = config["hours"]

    issue_times = generate_issue_times(
        horizon,
        config,
    )

    if not issue_times:
        raise ValueError(
            f"No valid issue times for {horizon}"
        )

    print(f"\nBACKTESTING {horizon.upper()}")
    print(f"Forecast hours per issue: {horizon_hours}")
    print(f"Forecast issue dates: {len(issue_times)}")

    all_results = []

    for index, issue_time in enumerate(
        issue_times,
        start=1,
    ):
        start_time = time.perf_counter()

        forecast_times = pd.date_range(
            start=issue_time,
            periods=horizon_hours,
            freq="h",
        )

        # Ground truth is used for scoring only.
        actual = demand_lookup.reindex(
            forecast_times
        ).to_numpy(dtype=float)

        if not np.isfinite(actual).all():
            raise ValueError(
                f"Missing actual demand: {issue_time}"
            )

        # The model sees only pre-issue observations.
        available_history = historical[
            historical["hour_start_utc"] < issue_time
        ].copy()

        recursive = forecast_multiple_hours(
            issue_time=issue_time,
            horizon=horizon,
            historical_data=available_history,
        )

        returned_times = pd.DatetimeIndex(
            pd.to_datetime(
                recursive["forecast_time_utc"],
                utc=True,
            )
        )

        if not returned_times.equals(forecast_times):
            raise ValueError(
                "Recursive forecast timestamp mismatch."
            )

        recursive_values = recursive[
            "predicted_demand_mw"
        ].to_numpy(dtype=float)

        naive_24h = seasonal_naive_forecast(
            demand_lookup,
            issue_time,
            horizon_hours,
            season_hours=24,
        )

        naive_168h = seasonal_naive_forecast(
            demand_lookup,
            issue_time,
            horizon_hours,
            season_hours=168,
        )

        # The last observed seasonal patterns must
        # match the available history exactly.
        assert (
            available_history["hour_start_utc"].max()
            < issue_time
        )

        result = pd.DataFrame({
            "horizon": horizon,
            "issue_time_utc": issue_time,
            "forecast_time_utc": forecast_times,
            "step": np.arange(
                1,
                horizon_hours + 1,
            ),
            "actual_demand_mw": actual,
            "recursive_ml_mw": recursive_values,
            "naive_24h_mw": naive_24h,
            "naive_168h_mw": naive_168h,
        })

        all_results.append(result)

        elapsed = time.perf_counter() - start_time

        print(
            f"Completed {index}/{len(issue_times)} "
            f"| {issue_time.date()} "
            f"| {elapsed:.2f}s"
        )

    results = pd.concat(
        all_results,
        ignore_index=True,
    )

    return results


def summarize_results(results):
    models = {
        "Recursive ML": "recursive_ml_mw",
        "Seasonal Naive 24h": "naive_24h_mw",
        "Seasonal Naive 168h": "naive_168h_mw",
    }

    overall_rows = []
    issue_rows = []
    block_rows = []

    for horizon, group in results.groupby(
        "horizon",
        sort=False,
    ):
        for model_name, column in models.items():
            metrics = calculate_metrics(
                group["actual_demand_mw"],
                group[column],
            )

            overall_rows.append({
                "horizon": horizon,
                "model": model_name,
                **metrics,
            })

        for issue_time, issue_group in group.groupby(
            "issue_time_utc"
        ):
            for model_name, column in models.items():
                metrics = calculate_metrics(
                    issue_group["actual_demand_mw"],
                    issue_group[column],
                )

                issue_rows.append({
                    "horizon": horizon,
                    "issue_time_utc": issue_time,
                    "model": model_name,
                    **metrics,
                })

        # Examine accuracy across successive
        # 24-hour forecast blocks.
        group = group.copy()

        group["forecast_day"] = (
            (group["step"] - 1) // 24
        ) + 1

        for day, day_group in group.groupby(
            "forecast_day"
        ):
            for model_name, column in models.items():
                metrics = calculate_metrics(
                    day_group["actual_demand_mw"],
                    day_group[column],
                )

                block_rows.append({
                    "horizon": horizon,
                    "forecast_day": int(day),
                    "model": model_name,
                    **metrics,
                })

    return (
        pd.DataFrame(overall_rows),
        pd.DataFrame(issue_rows),
        pd.DataFrame(block_rows),
    )


def main():
    print(
        "\nINNEVA.E — Long-Horizon Historical Backtest"
    )
    print("-------------------------------------------")

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    historical = load_historical_data()

    validate_historical_data(historical)

    demand_lookup = historical.set_index(
        "hour_start_utc"
    )["actual_load_mw"]

    experiment_results = []

    for horizon, config in EXPERIMENTS.items():
        results = evaluate_horizon(
            historical,
            demand_lookup,
            horizon,
            config,
        )

        experiment_results.append(results)

    predictions = pd.concat(
        experiment_results,
        ignore_index=True,
    )

    overall, by_issue, by_day = summarize_results(
        predictions
    )

    output_files = {
        "predictions.csv": predictions,
        "overall_metrics.csv": overall,
        "metrics_by_issue.csv": by_issue,
        "metrics_by_forecast_day.csv": by_day,
    }

    for filename, dataframe in output_files.items():
        dataframe.to_csv(
            OUTPUT_DIR / filename,
            index=False,
        )

    for horizon in EXPERIMENTS:
        print(f"\n{horizon.upper()} — OVERALL PERFORMANCE")

        summary = overall[
            overall["horizon"] == horizon
        ]

        print(
            summary.to_string(
                index=False,
                float_format=lambda x: f"{x:,.2f}",
            )
        )

        ml_mae = summary.loc[
            summary["model"] == "Recursive ML",
            "mae_mw",
        ].iloc[0]

        for baseline in [
            "Seasonal Naive 24h",
            "Seasonal Naive 168h",
        ]:
            baseline_mae = summary.loc[
                summary["model"] == baseline,
                "mae_mw",
            ].iloc[0]

            improvement = (
                (baseline_mae - ml_mae)
                / baseline_mae
                * 100
            )

            print(
                f"ML MAE improvement vs {baseline}: "
                f"{improvement:.2f}%"
            )

        ml_by_day = by_day[
            (by_day["horizon"] == horizon)
            & (by_day["model"] == "Recursive ML")
        ]

        print("\nRECURSIVE ML — ERROR BY FORECAST DAY")

        print(
            ml_by_day[
                ["forecast_day", "mae_mw", "rmse_mw"]
            ].to_string(
                index=False,
                float_format=lambda x: f"{x:,.2f}",
            )
        )

    print("\nBACKTEST SUMMARY")

    for horizon in EXPERIMENTS:
        group = predictions[
            predictions["horizon"] == horizon
        ]

        print(
            f"{horizon}: "
            f"{group['issue_time_utc'].nunique()} "
            f"forecast issues, "
            f"{len(group)} evaluated hours"
        )

    print(f"\nResults saved to: {OUTPUT_DIR}")
    print(
        "\nLONG-HORIZON BACKTEST COMPLETED SUCCESSFULLY"
    )


if __name__ == "__main__":
    main()
