
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "data/forecasting/energy_intelligence_hourly.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data/processed/direct_forecasting"
)

OUTPUT_FILE = OUTPUT_DIR / "direct_training_data.csv"

FIRST_ISSUE = pd.Timestamp(
    "2024-02-01T00:00:00+00:00"
)

LAST_ISSUE = pd.Timestamp(
    "2026-05-31T00:00:00+00:00"
)

TRAINING_DATA_CUTOFF = pd.Timestamp(
    "2026-07-01T00:00:00+00:00"
)

MAX_HORIZON_HOURS = 720


def load_demand():
    df = pd.read_csv(
        INPUT_FILE,
        usecols=["hour_start_utc", "actual_load_mw"],
    )

    df["hour_start_utc"] = pd.to_datetime(
        df["hour_start_utc"],
        utc=True,
    )

    df = df.sort_values(
        "hour_start_utc"
    ).reset_index(drop=True)

    if df["hour_start_utc"].duplicated().any():
        raise ValueError("Duplicate timestamps found.")

    expected = pd.date_range(
        start=df["hour_start_utc"].min(),
        end=df["hour_start_utc"].max(),
        freq="h",
    )

    if not pd.DatetimeIndex(
        df["hour_start_utc"]
    ).equals(expected):
        raise ValueError(
            "Historical timestamps are not continuous."
        )

    df["actual_load_mw"] = pd.to_numeric(
        df["actual_load_mw"],
        errors="coerce",
    )

    if not np.isfinite(
        df["actual_load_mw"].to_numpy()
    ).all():
        raise ValueError(
            "Historical demand contains invalid values."
        )

    return df.set_index(
        "hour_start_utc"
    )["actual_load_mw"]


def build_examples_for_issue(demand, issue_time):
    """
    Create direct forecasting examples.

    Every feature is computed using information
    available strictly before the issue time.

    Future actual demand is used only as the
    supervised-learning target.
    """

    historical = demand.loc[
        demand.index < issue_time
    ]

    if len(historical) < 168:
        raise ValueError(
            "Insufficient historical observations."
        )

    recent = historical.iloc[-168:]

    expected_latest = (
        issue_time - pd.Timedelta(hours=1)
    )

    if recent.index[-1] != expected_latest:
        raise ValueError(
            "Missing latest historical observation."
        )

    expected_history = pd.date_range(
        end=expected_latest,
        periods=168,
        freq="h",
    )

    if not recent.index.equals(expected_history):
        raise ValueError(
            "Historical window is not continuous."
        )

    # Features fixed at forecast issue time.
    issue_features = {
        "issue_hour": issue_time.hour,
        "issue_day_of_week": issue_time.day_of_week,
        "issue_month": issue_time.month,
        "issue_lag_1h": recent.iloc[-1],
        "issue_lag_24h": recent.iloc[-24],
        "issue_lag_168h": recent.iloc[-168],
        "issue_mean_24h": recent.iloc[-24:].mean(),
        "issue_mean_168h": recent.mean(),
        "issue_std_24h": recent.iloc[-24:].std(),
    }

    rows = []

    for lead in range(1, MAX_HORIZON_HOURS + 1):
        target_time = (
            issue_time
            + pd.Timedelta(hours=lead - 1)
        )

        if target_time >= TRAINING_DATA_CUTOFF:
            break

        if target_time not in demand.index:
            raise ValueError(
                f"Missing target: {target_time}"
            )

        # Repeat only the last fully observed
        # daily and weekly patterns.
        daily_offset = (lead - 1) % 24
        weekly_offset = (lead - 1) % 168

        daily_reference = (
            issue_time
            - pd.Timedelta(hours=24)
            + pd.Timedelta(hours=daily_offset)
        )

        weekly_reference = (
            issue_time
            - pd.Timedelta(hours=168)
            + pd.Timedelta(hours=weekly_offset)
        )

        if (
            daily_reference >= issue_time
            or weekly_reference >= issue_time
        ):
            raise AssertionError(
                "A seasonal feature uses future data."
            )

        row = {
            "issue_time_utc": issue_time,
            "target_time_utc": target_time,
            "lead_hours": lead,
            "target_hour": target_time.hour,
            "target_day_of_week": target_time.day_of_week,
            "target_month": target_time.month,
            "target_is_weekend": int(
                target_time.day_of_week >= 5
            ),
            "seasonal_daily_mw": demand.loc[
                daily_reference
            ],
            "seasonal_weekly_mw": demand.loc[
                weekly_reference
            ],
            **issue_features,
            "actual_load_mw": demand.loc[
                target_time
            ],
        }

        rows.append(row)

    return pd.DataFrame(rows)


def main():
    print(
        "\nINNEVA.E — Direct Forecast Training Data"
    )
    print("---------------------------------------")

    demand = load_demand()

    issue_times = pd.date_range(
        start=FIRST_ISSUE,
        end=LAST_ISSUE,
        freq="7D",
    )

    datasets = []

    for number, issue_time in enumerate(
        issue_times,
        start=1,
    ):
        examples = build_examples_for_issue(
            demand,
            issue_time,
        )

        datasets.append(examples)

        if (
            number == 1
            or number % 20 == 0
            or number == len(issue_times)
        ):
            print(
                f"Processed {number}/{len(issue_times)} "
                f"forecast origins"
            )

    dataset = pd.concat(
        datasets,
        ignore_index=True,
    )

    if dataset.empty:
        raise ValueError(
            "No training examples were generated."
        )

    if dataset["actual_load_mw"].isna().any():
        raise ValueError(
            "Missing training targets."
        )

    if (
        dataset["target_time_utc"]
        >= TRAINING_DATA_CUTOFF
    ).any():
        raise AssertionError(
            "Training targets extend into holdout."
        )

    if (
        dataset["target_time_utc"]
        < dataset["issue_time_utc"]
    ).any():
        raise AssertionError(
            "Target precedes forecast issue."
        )

    if dataset.duplicated(
        ["issue_time_utc", "lead_hours"]
    ).any():
        raise AssertionError(
            "Duplicate forecast training examples."
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataset.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print("\nDATASET SUMMARY")
    print(f"Training examples: {len(dataset):,}")
    print(
        f"Forecast origins: "
        f"{dataset['issue_time_utc'].nunique():,}"
    )
    print(
        f"Feature/metadata columns: "
        f"{len(dataset.columns)}"
    )
    print(
        f"Maximum lead: "
        f"{dataset['lead_hours'].max()} hours"
    )
    print(
        f"Latest target: "
        f"{dataset['target_time_utc'].max()}"
    )

    print("\nFIRST FIVE EXAMPLES")
    print(
        dataset[
            [
                "issue_time_utc",
                "target_time_utc",
                "lead_hours",
                "seasonal_daily_mw",
                "seasonal_weekly_mw",
                "actual_load_mw",
            ]
        ].head().to_string(index=False)
    )

    print(f"\nSaved to: {OUTPUT_FILE}")

    print(
        "\nDIRECT TRAINING DATASET COMPLETED SUCCESSFULLY"
    )


if __name__ == "__main__":
    main()
