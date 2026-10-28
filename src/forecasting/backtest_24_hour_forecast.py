
from pathlib import Path

import numpy as np
import pandas as pd

from one_hour_forecast import load_historical_data
from multi_hour_forecast import forecast_multiple_hours


PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/recursive_24h_backtest"
)

HOLDOUT_START = pd.Timestamp(
    "2026-07-01T00:00:00+00:00"
)

HOLDOUT_END_EXCLUSIVE = pd.Timestamp(
    "2026-10-01T00:00:00+00:00"
)


def calculate_metrics(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    if len(actual) == 0:
        raise ValueError("Cannot evaluate empty predictions.")

    if not (
        np.isfinite(actual).all()
        and np.isfinite(predicted).all()
    ):
        raise ValueError("Metrics require finite values.")

    error = actual - predicted

    mae = np.mean(np.abs(error))
    rmse = np.sqrt(np.mean(error ** 2))

    nonzero = actual != 0

    mape = (
        np.mean(
            np.abs(error[nonzero] / actual[nonzero])
        ) * 100
        if nonzero.any()
        else np.nan
    )

    return {
        "mae_mw": float(mae),
        "rmse_mw": float(rmse),
        "mape_pct": float(mape),
    }


def validate_history(df):
    if df["hour_start_utc"].duplicated().any():
        raise ValueError(
            "Historical data contains duplicate timestamps."
        )

    timestamps = pd.DatetimeIndex(
        df["hour_start_utc"]
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

    if df["actual_load_mw"].isna().any():
        raise ValueError(
            "Historical demand contains missing values."
        )


def run_backtest():
    print("\nINNEVA.E — 24-Hour Historical Backtest")
    print("--------------------------------------")

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    historical = load_historical_data()

    validate_history(historical)

    demand_lookup = historical.set_index(
        "hour_start_utc"
    )["actual_load_mw"]

    issue_times = pd.date_range(
        start=HOLDOUT_START,
        end=HOLDOUT_END_EXCLUSIVE,
        freq="D",
        inclusive="left",
    )

    all_predictions = []

    for index, issue_time in enumerate(
        issue_times,
        start=1,
    ):
        forecast_times = pd.date_range(
            start=issue_time,
            periods=24,
            freq="h",
        )

        # Actual demand is used only for evaluation.
        actual = demand_lookup.reindex(
            forecast_times
        )

        if actual.isna().any():
            raise ValueError(
                f"Missing actual demand for {issue_time}"
            )

        # Use only data strictly before issue time.
        available_history = historical[
            historical["hour_start_utc"] < issue_time
        ].copy()

        # Recursive model predictions.
        recursive = forecast_multiple_hours(
            issue_time=issue_time,
            horizon="24h",
            historical_data=available_history,
        )

        recursive_times = pd.DatetimeIndex(
            pd.to_datetime(
                recursive["forecast_time_utc"],
                utc=True,
            )
        )

        if not recursive_times.equals(forecast_times):
            raise ValueError(
                "Recursive forecast timestamps "
                "do not match evaluation timestamps."
            )

        # Previous-day baseline.
        previous_day_times = (
            forecast_times - pd.Timedelta(hours=24)
        )

        naive_24h = demand_lookup.reindex(
            previous_day_times
        )

        # Previous-week baseline.
        previous_week_times = (
            forecast_times - pd.Timedelta(hours=168)
        )

        naive_168h = demand_lookup.reindex(
            previous_week_times
        )

        if (
            naive_24h.isna().any()
            or naive_168h.isna().any()
        ):
            raise ValueError(
                f"Missing baseline observations "
                f"for {issue_time}"
            )

        day_results = pd.DataFrame({
            "issue_time_utc": issue_time,
            "forecast_time_utc": forecast_times,
            "step": np.arange(1, 25),
            "actual_demand_mw": actual.to_numpy(),
            "recursive_ml_mw": recursive[
                "predicted_demand_mw"
            ].to_numpy(),
            "naive_24h_mw": naive_24h.to_numpy(),
            "naive_168h_mw": naive_168h.to_numpy(),
        })

        all_predictions.append(day_results)

        if (
            index == 1
            or index % 10 == 0
            or index == len(issue_times)
        ):
            print(
                f"Completed {index}/{len(issue_times)} "
                f"forecast dates"
            )

    results = pd.concat(
        all_predictions,
        ignore_index=True,
    )

    predictions_file = (
        OUTPUT_DIR / "backtest_predictions.csv"
    )

    results.to_csv(
        predictions_file,
        index=False,
    )

    models = {
        "Recursive ML": "recursive_ml_mw",
        "Seasonal Naive 24h": "naive_24h_mw",
        "Seasonal Naive 168h": "naive_168h_mw",
    }

    # Overall metrics.
    overall_rows = []

    for model_name, column in models.items():
        metrics = calculate_metrics(
            results["actual_demand_mw"],
            results[column],
        )

        overall_rows.append({
            "model": model_name,
            **metrics,
        })

    overall = pd.DataFrame(overall_rows)

    overall_file = (
        OUTPUT_DIR / "overall_metrics.csv"
    )

    overall.to_csv(
        overall_file,
        index=False,
    )

    # Metrics by forecast step.
    step_rows = []

    for step in range(1, 25):
        step_data = results[
            results["step"] == step
        ]

        for model_name, column in models.items():
            metrics = calculate_metrics(
                step_data["actual_demand_mw"],
                step_data[column],
            )

            step_rows.append({
                "step": step,
                "model": model_name,
                **metrics,
            })

    step_metrics = pd.DataFrame(step_rows)

    step_file = (
        OUTPUT_DIR / "metrics_by_step.csv"
    )

    step_metrics.to_csv(
        step_file,
        index=False,
    )

    # Metrics by forecast issue date.
    daily_rows = []

    for issue_time, group in results.groupby(
        "issue_time_utc"
    ):
        for model_name, column in models.items():
            metrics = calculate_metrics(
                group["actual_demand_mw"],
                group[column],
            )

            daily_rows.append({
                "issue_time_utc": issue_time,
                "model": model_name,
                **metrics,
            })

    daily_metrics = pd.DataFrame(daily_rows)

    daily_file = (
        OUTPUT_DIR / "metrics_by_day.csv"
    )

    daily_metrics.to_csv(
        daily_file,
        index=False,
    )

    # Print results.
    print("\nOVERALL PERFORMANCE")
    print(
        overall.to_string(
            index=False,
            float_format=lambda x: f"{x:,.2f}",
        )
    )

    ml_mae = overall.loc[
        overall["model"] == "Recursive ML",
        "mae_mw",
    ].iloc[0]

    for baseline in [
        "Seasonal Naive 24h",
        "Seasonal Naive 168h",
    ]:
        baseline_mae = overall.loc[
            overall["model"] == baseline,
            "mae_mw",
        ].iloc[0]

        improvement = (
            (baseline_mae - ml_mae)
            / baseline_mae
            * 100
        )

        print(
            f"\nML MAE improvement vs {baseline}: "
            f"{improvement:.2f}%"
        )

    print("\nRECURSIVE ML ERROR BY FORECAST STEP")

    ml_steps = step_metrics[
        step_metrics["model"] == "Recursive ML"
    ][["step", "mae_mw", "rmse_mw"]]

    print(
        ml_steps.to_string(
            index=False,
            float_format=lambda x: f"{x:,.2f}",
        )
    )

    print("\nBACKTEST SUMMARY")
    print(f"Forecast dates: {len(issue_times)}")
    print(f"Evaluated hours: {len(results)}")
    print(f"First issue time: {issue_times[0]}")
    print(f"Last issue time: {issue_times[-1]}")

    print("\nOUTPUT FILES")
    print(predictions_file)
    print(overall_file)
    print(step_file)
    print(daily_file)

    print("\n24-HOUR BACKTEST COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    run_backtest()
