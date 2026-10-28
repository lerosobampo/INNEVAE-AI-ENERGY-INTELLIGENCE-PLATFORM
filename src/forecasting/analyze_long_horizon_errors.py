
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "data/processed/long_horizon_backtest"
    / "predictions.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/long_horizon_diagnostics"
)


def prepare_data():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Backtest predictions not found: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    required = [
        "horizon",
        "issue_time_utc",
        "forecast_time_utc",
        "step",
        "actual_demand_mw",
        "recursive_ml_mw",
        "naive_168h_mw",
    ]

    missing = set(required) - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing columns: {sorted(missing)}"
        )

    df["issue_time_utc"] = pd.to_datetime(
        df["issue_time_utc"],
        utc=True,
    )

    df["forecast_time_utc"] = pd.to_datetime(
        df["forecast_time_utc"],
        utc=True,
    )

    for column in [
        "actual_demand_mw",
        "recursive_ml_mw",
        "naive_168h_mw",
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="raise",
        )

        if not np.isfinite(df[column]).all():
            raise ValueError(
                f"Invalid values in {column}"
            )

    df["ml_error_mw"] = (
        df["recursive_ml_mw"]
        - df["actual_demand_mw"]
    )

    df["ml_absolute_error_mw"] = (
        df["ml_error_mw"].abs()
    )

    df["weekly_absolute_error_mw"] = (
        df["naive_168h_mw"]
        - df["actual_demand_mw"]
    ).abs()

    df["forecast_day"] = (
        (df["step"] - 1) // 24 + 1
    )

    return df


def analyze_issue_dates(df):
    rows = []

    for (horizon, issue_time), group in df.groupby(
        ["horizon", "issue_time_utc"]
    ):
        ml_mae = group[
            "ml_absolute_error_mw"
        ].mean()

        weekly_mae = group[
            "weekly_absolute_error_mw"
        ].mean()

        improvement = (
            (weekly_mae - ml_mae)
            / weekly_mae * 100
            if weekly_mae > 0
            else np.nan
        )

        rows.append({
            "horizon": horizon,
            "issue_time_utc": issue_time,
            "ml_mae_mw": ml_mae,
            "weekly_naive_mae_mw": weekly_mae,
            "ml_bias_mw": group[
                "ml_error_mw"
            ].mean(),
            "ml_improvement_pct": improvement,
            "ml_wins": ml_mae < weekly_mae,
        })

    return pd.DataFrame(rows).sort_values(
        ["horizon", "issue_time_utc"]
    )


def analyze_forecast_days(df):
    return (
        df.groupby(
            ["horizon", "forecast_day"]
        )
        .agg(
            ml_mae_mw=(
                "ml_absolute_error_mw",
                "mean",
            ),
            weekly_naive_mae_mw=(
                "weekly_absolute_error_mw",
                "mean",
            ),
            ml_bias_mw=(
                "ml_error_mw",
                "mean",
            ),
            evaluated_hours=(
                "step",
                "size",
            ),
        )
        .reset_index()
    )


def analyze_horizon_summary(df, by_issue):
    rows = []

    for horizon, group in df.groupby("horizon"):
        issues = by_issue[
            by_issue["horizon"] == horizon
        ]

        rows.append({
            "horizon": horizon,
            "forecast_issues": len(issues),
            "evaluated_hours": len(group),
            "ml_mae_mw": group[
                "ml_absolute_error_mw"
            ].mean(),
            "weekly_naive_mae_mw": group[
                "weekly_absolute_error_mw"
            ].mean(),
            "ml_bias_mw": group[
                "ml_error_mw"
            ].mean(),
            "ml_win_count": int(
                issues["ml_wins"].sum()
            ),
            "ml_win_rate_pct": (
                issues["ml_wins"].mean() * 100
            ),
        })

    return pd.DataFrame(rows)


def main():
    print(
        "\nINNEVA.E — Long-Horizon Error Diagnostics"
    )
    print("----------------------------------------")

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = prepare_data()

    by_issue = analyze_issue_dates(df)
    by_day = analyze_forecast_days(df)
    summary = analyze_horizon_summary(
        df,
        by_issue,
    )

    summary.to_csv(
        OUTPUT_DIR / "diagnostic_summary.csv",
        index=False,
    )

    by_issue.to_csv(
        OUTPUT_DIR / "diagnostics_by_issue.csv",
        index=False,
    )

    by_day.to_csv(
        OUTPUT_DIR / "diagnostics_by_day.csv",
        index=False,
    )

    for horizon in ["7d", "30d"]:
        print(f"\n{'=' * 50}")
        print(f"{horizon.upper()} DIAGNOSTICS")
        print(f"{'=' * 50}")

        horizon_summary = summary[
            summary["horizon"] == horizon
        ]

        if horizon_summary.empty:
            continue

        print("\nOVERALL SUMMARY")
        print(
            horizon_summary.to_string(
                index=False,
                float_format=lambda x: f"{x:,.2f}",
            )
        )

        issues = by_issue[
            by_issue["horizon"] == horizon
        ].copy()

        print("\nPERFORMANCE BY ISSUE DATE")
        print(
            issues.to_string(
                index=False,
                float_format=lambda x: f"{x:,.2f}",
            )
        )

        print("\nTHREE WORST ISSUE DATES")
        print(
            issues.nlargest(
                3,
                "ml_mae_mw",
            )[
                [
                    "issue_time_utc",
                    "ml_mae_mw",
                    "weekly_naive_mae_mw",
                    "ml_bias_mw",
                ]
            ].to_string(
                index=False,
                float_format=lambda x: f"{x:,.2f}",
            )
        )

        days = by_day[
            by_day["horizon"] == horizon
        ]

        print("\nFIRST FIVE FORECAST DAYS")
        print(
            days.head(5).to_string(
                index=False,
                float_format=lambda x: f"{x:,.2f}",
            )
        )

        print("\nLAST FIVE FORECAST DAYS")
        print(
            days.tail(5).to_string(
                index=False,
                float_format=lambda x: f"{x:,.2f}",
            )
        )

    print("\nDIAGNOSTIC FILES SAVED TO:")
    print(OUTPUT_DIR)

    print(
        "\nLONG-HORIZON DIAGNOSTICS COMPLETED SUCCESSFULLY"
    )


if __name__ == "__main__":
    main()
