
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    ROOT
    / "data/processed/architecture_comparison"
    / "comparison_predictions.csv"
)

OUTPUT_DIR = (
    ROOT
    / "data/processed/architecture_stability"
)

HORIZONS = {
    "24h": 24,
    "7d": 168,
    "30d": 720,
}

MODELS = {
    "Recursive ML": "recursive_ml_mw",
    "Direct ML": "direct_ml_mw",
    "Daily naive": "seasonal_daily_mw",
    "Weekly naive": "seasonal_weekly_mw",
}


def load_data():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(INPUT_FILE)

    df = pd.read_csv(INPUT_FILE)

    required = [
        "issue_time_utc",
        "target_time_utc",
        "lead_hours",
        "actual_load_mw",
        *MODELS.values(),
    ]

    missing = set(required) - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing columns: {sorted(missing)}"
        )

    for column in [
        "issue_time_utc",
        "target_time_utc",
    ]:
        df[column] = pd.to_datetime(
            df[column],
            utc=True,
        )

    numeric_columns = [
        "lead_hours",
        "actual_load_mw",
        *MODELS.values(),
    ]

    df[numeric_columns] = df[
        numeric_columns
    ].apply(pd.to_numeric, errors="raise")

    if not np.isfinite(
        df[numeric_columns].to_numpy(dtype=float)
    ).all():
        raise ValueError(
            "Invalid numeric values found."
        )

    if df.duplicated(
        ["issue_time_utc", "lead_hours"]
    ).any():
        raise ValueError(
            "Duplicate forecast predictions."
        )

    return df


def calculate_mae(group, prediction_column):
    return float(
        np.mean(
            np.abs(
                group["actual_load_mw"].to_numpy()
                - group[prediction_column].to_numpy()
            )
        )
    )


def analyze_horizon(df, horizon, hours):
    subset = df[
        df["lead_hours"] <= hours
    ].copy()

    rows = []

    for issue_time, group in subset.groupby(
        "issue_time_utc"
    ):
        if len(group) != hours:
            raise ValueError(
                f"Incomplete forecast: {issue_time}"
            )

        row = {
            "horizon": horizon,
            "issue_time_utc": issue_time,
        }

        for name, column in MODELS.items():
            row[name] = calculate_mae(
                group,
                column,
            )

        row["winner"] = min(
            MODELS,
            key=lambda name: row[name],
        )

        rows.append(row)

    by_issue = pd.DataFrame(rows)

    summary_rows = []

    for name in MODELS:
        values = by_issue[name]

        summary_rows.append({
            "horizon": horizon,
            "model": name,
            "mean_issue_mae_mw": values.mean(),
            "median_issue_mae_mw": values.median(),
            "worst_issue_mae_mw": values.max(),
            "best_issue_mae_mw": values.min(),
            "win_count": int(
                (by_issue["winner"] == name).sum()
            ),
            "issue_count": len(by_issue),
        })

    summary = pd.DataFrame(summary_rows)

    return by_issue, summary


def main():
    print(
        "\nINNEVA.E — Architecture Stability Analysis"
    )
    print("------------------------------------------")

    df = load_data()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_issues = []
    all_summaries = []

    for horizon, hours in HORIZONS.items():
        by_issue, summary = analyze_horizon(
            df,
            horizon,
            hours,
        )

        all_issues.append(by_issue)
        all_summaries.append(summary)

        print(f"\n{horizon.upper()} — STABILITY SUMMARY")

        print(
            summary.to_string(
                index=False,
                float_format=lambda x: f"{x:,.2f}",
            )
        )

        print("\nWINNER BY FORECAST ISSUE")

        print(
            by_issue[
                ["issue_time_utc", "winner"]
            ].to_string(index=False)
        )

        recursive = by_issue["Recursive ML"]
        direct = by_issue["Direct ML"]

        print("\nDIRECT VS RECURSIVE")

        print(
            "Direct wins: "
            f"{int((direct < recursive).sum())}"
        )

        print(
            "Recursive wins: "
            f"{int((recursive < direct).sum())}"
        )

        print(
            "Average direct minus recursive MAE: "
            f"{(direct - recursive).mean():,.2f} MW"
        )

    issues_df = pd.concat(
        all_issues,
        ignore_index=True,
    )

    summaries_df = pd.concat(
        all_summaries,
        ignore_index=True,
    )

    issues_df.to_csv(
        OUTPUT_DIR / "stability_by_issue.csv",
        index=False,
    )

    summaries_df.to_csv(
        OUTPUT_DIR / "stability_summary.csv",
        index=False,
    )

    print("\nRESULTS SAVED TO:")
    print(OUTPUT_DIR)

    print(
        "\nARCHITECTURE STABILITY ANALYSIS COMPLETED"
    )


if __name__ == "__main__":
    main()
