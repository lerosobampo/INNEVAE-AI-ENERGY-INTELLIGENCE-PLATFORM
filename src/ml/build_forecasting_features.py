
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "data/development/energy_intelligence_dev_90d.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data/development/demand_features_90d.csv"
)


def build_features(df):
    df = df.copy()

    # Convert timestamps into timezone-aware datetime objects.
    df["hour_start_utc"] = pd.to_datetime(
        df["hour_start_utc"],
        utc=True
    )

    # Ensure correct chronological order.
    df = df.sort_values("hour_start_utc").reset_index(drop=True)

    # Verify hourly continuity before using row-based shifts.
    timestamps = df["hour_start_utc"]
    assert timestamps.is_unique, "Duplicate timestamps detected."
    assert timestamps.diff().dropna().eq(
        pd.Timedelta(hours=1)
    ).all(), "Missing or irregular hourly timestamps detected."

    # Target variable.
    target = df["actual_load_mw"]

    # Historical demand lags.
    df["demand_lag_1h"] = target.shift(1)
    df["demand_lag_24h"] = target.shift(24)
    df["demand_lag_168h"] = target.shift(168)

    # Shift before calculating rolling statistics.
    previous_demand = target.shift(1)

    df["demand_rolling_mean_24h"] = (
        previous_demand.rolling(window=24).mean()
    )

    df["demand_rolling_mean_168h"] = (
        previous_demand.rolling(window=168).mean()
    )

    df["demand_rolling_std_24h"] = (
        previous_demand.rolling(window=24).std()
    )

    return df


def main():
    print("\nINNEVA.E — Demand Feature Engineering")

    df = pd.read_csv(INPUT_FILE)

    print(f"Input records: {len(df):,}")

    featured_df = build_features(df)

    feature_columns = [
        "demand_lag_1h",
        "demand_lag_24h",
        "demand_lag_168h",
        "demand_rolling_mean_24h",
        "demand_rolling_mean_168h",
        "demand_rolling_std_24h",
    ]

    # Retain the full dataset for traceability.
    # Missing lag values are expected at the beginning.
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    featured_df.to_csv(OUTPUT_FILE, index=False)

    print(f"Output records: {len(featured_df):,}")
    print(f"Output columns: {len(featured_df.columns)}")
    print(f"Saved to: {OUTPUT_FILE}")

    print("\nMissing values in new features:")
    print(featured_df[feature_columns].isna().sum())

    print("\nFirst complete feature record:")
    complete = featured_df.dropna(subset=feature_columns)
    print(
        complete[
            ["hour_start_utc", "actual_load_mw"] + feature_columns
        ].head(1).to_string(index=False)
    )


if __name__ == "__main__":
    main()
