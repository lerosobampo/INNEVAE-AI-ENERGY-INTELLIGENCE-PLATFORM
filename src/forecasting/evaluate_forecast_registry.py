
"""
INNEVA.E — Registered Forecast Evaluation
Module 17.7B.1

Read-only evaluation of registered electricity demand forecasts.

- Joins forecasts to observed hourly demand
- Reports pending actuals separately
- Calculates MAE, RMSE, MAPE and signed bias
- Distinguishes retrospective from operational forecasts
- Saves evaluation reports as CSV files
- Does not modify the forecast registry or historical data
"""

from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

REGISTRY_PATH = (
    PROJECT_ROOT
    / "data/forecasting/forecast_registry.sqlite"
)

HISTORICAL_PATH = (
    PROJECT_ROOT
    / "data/forecasting/energy_intelligence_hourly.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/forecast_evaluation"
)


def load_registered_predictions():
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"Forecast registry not found: {REGISTRY_PATH}"
        )

    query = """
        SELECT
            r.forecast_id,
            r.created_at_utc,
            r.issue_time_utc,
            r.horizon,
            r.requested_method,
            r.selected_method,
            r.model_version,
            p.forecast_time_utc,
            p.step,
            p.predicted_demand_mw
        FROM forecast_runs AS r
        INNER JOIN forecast_predictions AS p
            ON r.forecast_id = p.forecast_id
        ORDER BY r.created_at_utc, r.forecast_id, p.step
    """

    with sqlite3.connect(
        f"file:{REGISTRY_PATH}?mode=ro",
        uri=True,
    ) as connection:
        forecasts = pd.read_sql_query(query, connection)

    for column in [
        "created_at_utc",
        "issue_time_utc",
        "forecast_time_utc",
    ]:
        forecasts[column] = pd.to_datetime(
            forecasts[column],
            utc=True,
            errors="raise",
        )

    return forecasts


def load_actual_demand():
    if not HISTORICAL_PATH.exists():
        raise FileNotFoundError(
            f"Historical data not found: {HISTORICAL_PATH}"
        )

    actuals = pd.read_csv(HISTORICAL_PATH)

    required = {"hour_start_utc", "actual_load_mw"}

    missing = required - set(actuals.columns)

    if missing:
        raise ValueError(
            f"Missing historical columns: {sorted(missing)}"
        )

    actuals = actuals[
        ["hour_start_utc", "actual_load_mw"]
    ].copy()

    actuals["forecast_time_utc"] = pd.to_datetime(
        actuals["hour_start_utc"],
        utc=True,
        errors="raise",
    )

    actuals["actual_demand_mw"] = pd.to_numeric(
        actuals["actual_load_mw"],
        errors="coerce",
    )

    if actuals["forecast_time_utc"].duplicated().any():
        raise ValueError(
            "Duplicate timestamps in historical demand."
        )

    actuals = actuals[
        ["forecast_time_utc", "actual_demand_mw"]
    ]

    return actuals


def calculate_metrics(group):
    valid = group.loc[
        group["evaluation_status"] == "evaluated"
    ]

    total = len(group)
    evaluated = len(valid)
    pending = total - evaluated

    result = {
        "prediction_count": total,
        "evaluated_count": evaluated,
        "pending_count": pending,
        "coverage_pct": (
            100 * evaluated / total if total else np.nan
        ),
        "mae_mw": np.nan,
        "rmse_mw": np.nan,
        "mape_pct": np.nan,
        "bias_mw": np.nan,
    }

    if evaluated == 0:
        return result

    error = (
        valid["predicted_demand_mw"].to_numpy(dtype=float)
        - valid["actual_demand_mw"].to_numpy(dtype=float)
    )

    actual = valid[
        "actual_demand_mw"
    ].to_numpy(dtype=float)

    result["mae_mw"] = float(
        np.mean(np.abs(error))
    )

    result["rmse_mw"] = float(
        np.sqrt(np.mean(np.square(error)))
    )

    result["bias_mw"] = float(
        np.mean(error)
    )

    nonzero = actual != 0

    if nonzero.any():
        result["mape_pct"] = float(
            100 * np.mean(
                np.abs(error[nonzero] / actual[nonzero])
            )
        )

    return result


def evaluate_registry():
    forecasts = load_registered_predictions()
    actuals = load_actual_demand()

    if forecasts.empty:
        print("No registered forecasts found.")
        return None, None

    evaluated = forecasts.merge(
        actuals,
        on="forecast_time_utc",
        how="left",
        validate="many_to_one",
    )

    valid_actual = (
        np.isfinite(evaluated["actual_demand_mw"])
        & (evaluated["actual_demand_mw"] > 0)
    )

    evaluated["evaluation_status"] = np.where(
        valid_actual,
        "evaluated",
        "pending_actual",
    )

    # A forecast created after its issue time cannot
    # be classified as a contemporaneous operational run.
    evaluated["forecast_origin_type"] = np.where(
        evaluated["created_at_utc"]
        > evaluated["issue_time_utc"],
        "retrospective",
        "created_at_or_before_issue",
    )

    evaluated["error_mw"] = np.where(
        valid_actual,
        evaluated["predicted_demand_mw"]
        - evaluated["actual_demand_mw"],
        np.nan,
    )

    evaluated["absolute_error_mw"] = (
        evaluated["error_mw"].abs()
    )

    evaluated["absolute_percentage_error"] = np.where(
        valid_actual,
        100
        * evaluated["absolute_error_mw"]
        / evaluated["actual_demand_mw"],
        np.nan,
    )

    group_columns = [
        "forecast_id",
        "created_at_utc",
        "issue_time_utc",
        "horizon",
        "requested_method",
        "selected_method",
        "model_version",
        "forecast_origin_type",
    ]

    summaries = []

    for key, group in evaluated.groupby(
        group_columns,
        dropna=False,
        sort=False,
    ):
        summary = dict(zip(group_columns, key))
        summary.update(calculate_metrics(group))
        summaries.append(summary)

    summary_df = pd.DataFrame(summaries)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    evaluated.to_csv(
        OUTPUT_DIR / "registered_predictions_evaluated.csv",
        index=False,
    )

    summary_df.to_csv(
        OUTPUT_DIR / "registered_forecast_summary.csv",
        index=False,
    )

    return evaluated, summary_df


def main():
    print(
        "\nINNEVA.E — Registered Forecast Evaluation"
    )
    print("-----------------------------------------")

    evaluated, summary = evaluate_registry()

    if evaluated is None:
        return

    print("\nEVALUATION SUMMARY")

    print(
        f"Registered forecast runs: "
        f"{len(summary):,}"
    )

    print(
        f"Total predictions: "
        f"{len(evaluated):,}"
    )

    print(
        "Predictions with actuals: "
        f"{(evaluated['evaluation_status'] == 'evaluated').sum():,}"
    )

    print(
        "Predictions pending actuals: "
        f"{(evaluated['evaluation_status'] == 'pending_actual').sum():,}"
    )

    print("\nFORECAST RESULTS")

    columns = [
        "forecast_id",
        "horizon",
        "selected_method",
        "forecast_origin_type",
        "evaluated_count",
        "pending_count",
        "mae_mw",
        "rmse_mw",
        "mape_pct",
        "bias_mw",
    ]

    print(
        summary[columns].to_string(
            index=False,
            float_format=lambda value: f"{value:,.2f}",
        )
    )

    print("\nREPORTS SAVED TO")
    print(OUTPUT_DIR)

    print("\nEVALUATION COMPLETE")


if __name__ == "__main__":
    main()
