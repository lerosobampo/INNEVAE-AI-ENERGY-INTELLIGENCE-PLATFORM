
from pathlib import Path
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingRegressor


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_FILE = (
    PROJECT_ROOT
    / "data/processed/direct_forecasting/direct_training_data.csv"
)

MODEL_FILE = (
    PROJECT_ROOT
    / "models/direct_demand_final.joblib"
)

REPORT_DIR = (
    PROJECT_ROOT
    / "data/processed/direct_forecasting/final_training"
)

REPORT_FILE = REPORT_DIR / "training_summary.csv"


# ============================================================
# CONFIGURATION
# ============================================================

TRAINING_CUTOFF = pd.Timestamp(
    "2026-07-01T00:00:00+00:00"
)

MAX_HORIZON_HOURS = 720

FEATURES = [
    "lead_hours",
    "target_hour",
    "target_day_of_week",
    "target_month",
    "target_is_weekend",
    "seasonal_daily_mw",
    "seasonal_weekly_mw",
    "issue_hour",
    "issue_day_of_week",
    "issue_month",
    "issue_lag_1h",
    "issue_lag_24h",
    "issue_lag_168h",
    "issue_mean_24h",
    "issue_mean_168h",
    "issue_std_24h",
]

TARGET = "actual_load_mw"

MODEL_PARAMETERS = {
    "max_iter": 200,
    "learning_rate": 0.05,
    "max_leaf_nodes": 15,
    "l2_regularization": 1.0,
    "random_state": 42,
}


# ============================================================
# LOAD AND VALIDATE DATA
# ============================================================

def load_training_data():

    print("\nLOADING DIRECT FORECASTING DATA")

    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Training dataset not found: {DATA_FILE}"
        )

    df = pd.read_csv(DATA_FILE)

    required_columns = (
        FEATURES
        + [
            TARGET,
            "issue_time_utc",
            "target_time_utc",
        ]
    )

    missing_columns = (
        set(required_columns) - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            f"{sorted(missing_columns)}"
        )

    for column in [
        "issue_time_utc",
        "target_time_utc",
    ]:
        df[column] = pd.to_datetime(
            df[column],
            utc=True,
            errors="raise",
        )

    if df[
        ["issue_time_utc", "target_time_utc"]
    ].isna().any().any():
        raise ValueError(
            "Missing forecast timestamps."
        )

    numeric_columns = FEATURES + [TARGET]

    df[numeric_columns] = df[
        numeric_columns
    ].apply(
        pd.to_numeric,
        errors="raise",
    )

    if not np.isfinite(
        df[numeric_columns].to_numpy(dtype=float)
    ).all():
        raise ValueError(
            "Training data contains non-finite values."
        )

    if df.duplicated(
        ["issue_time_utc", "lead_hours"]
    ).any():
        raise ValueError(
            "Duplicate forecast training examples."
        )

    expected_target_time = (
        df["issue_time_utc"]
        + pd.to_timedelta(
            df["lead_hours"] - 1,
            unit="h",
        )
    )

    if not (
        df["target_time_utc"] == expected_target_time
    ).all():
        raise ValueError(
            "Target timestamps do not match lead hours."
        )

    if not (
        df["lead_hours"].between(
            1,
            MAX_HORIZON_HOURS,
        )
    ).all():
        raise ValueError(
            "Invalid forecast lead hours."
        )

    if (
        df["target_time_utc"] >= TRAINING_CUTOFF
    ).any():
        raise AssertionError(
            "Training data contains July–September "
            "evaluation targets."
        )

    if (
        df["issue_time_utc"] >= TRAINING_CUTOFF
    ).any():
        raise AssertionError(
            "Training data contains future issue times."
        )

    df = df.sort_values(
        ["issue_time_utc", "lead_hours"]
    ).reset_index(drop=True)

    print(f"Training examples: {len(df):,}")

    print(
        "Forecast origins: "
        f"{df['issue_time_utc'].nunique():,}"
    )

    print(
        "Earliest forecast origin: "
        f"{df['issue_time_utc'].min()}"
    )

    print(
        "Latest forecast origin: "
        f"{df['issue_time_utc'].max()}"
    )

    print(
        "Latest training target: "
        f"{df['target_time_utc'].max()}"
    )

    return df


# ============================================================
# TRAIN MODEL
# ============================================================

def train_model(df):

    print("\nTRAINING FINAL DIRECT MODEL")

    model = HistGradientBoostingRegressor(
        **MODEL_PARAMETERS
    )

    X = df[FEATURES].astype(float)
    y = df[TARGET].astype(float)

    model.fit(X, y)

    print("Model training completed.")

    # Verify model inference on a small sample.
    sample_predictions = model.predict(
        X.head(10)
    )

    if not np.isfinite(
        sample_predictions
    ).all():
        raise ValueError(
            "Model produced invalid predictions."
        )

    if (sample_predictions <= 0).any():
        raise ValueError(
            "Model produced non-positive demand."
        )

    print("Inference sanity check passed.")

    return model


# ============================================================
# SAVE MODEL
# ============================================================

def save_model(model, df):

    MODEL_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Never silently overwrite an existing model.
    if MODEL_FILE.exists():
        raise FileExistsError(
            "Final direct model already exists. "
            f"Existing file preserved: {MODEL_FILE}"
        )

    artifact = {
        "model": model,
        "features": FEATURES,
        "target": TARGET,
        "model_type": "direct_multi_horizon",
        "maximum_horizon_hours": MAX_HORIZON_HOURS,
        "training_cutoff_utc": str(
            TRAINING_CUTOFF
        ),
        "training_target_end_utc": str(
            df["target_time_utc"].max()
        ),
        "training_issue_start_utc": str(
            df["issue_time_utc"].min()
        ),
        "training_issue_end_utc": str(
            df["issue_time_utc"].max()
        ),
        "training_examples": len(df),
        "training_origins": df[
            "issue_time_utc"
        ].nunique(),
        "model_parameters": MODEL_PARAMETERS,
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    joblib.dump(
        artifact,
        MODEL_FILE,
    )

    print(f"\nMODEL SAVED TO:\n{MODEL_FILE}")

    return artifact


# ============================================================
# SAVE TRAINING REPORT
# ============================================================

def save_training_report(artifact):

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary = pd.DataFrame([
        {
            "model_type": artifact["model_type"],
            "training_examples": artifact[
                "training_examples"
            ],
            "training_origins": artifact[
                "training_origins"
            ],
            "training_issue_start_utc": artifact[
                "training_issue_start_utc"
            ],
            "training_issue_end_utc": artifact[
                "training_issue_end_utc"
            ],
            "training_target_end_utc": artifact[
                "training_target_end_utc"
            ],
            "maximum_horizon_hours": artifact[
                "maximum_horizon_hours"
            ],
            "feature_count": len(
                artifact["features"]
            ),
            "model_file": str(MODEL_FILE),
            "created_at_utc": artifact[
                "created_at_utc"
            ],
        }
    ])

    summary.to_csv(
        REPORT_FILE,
        index=False,
    )

    print(
        f"\nTRAINING REPORT SAVED TO:\n{REPORT_FILE}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\nINNEVA.E — Final Direct Forecast Model"
    )

    print(
        "--------------------------------------"
    )

    # Check before spending time training.
    if MODEL_FILE.exists():
        raise FileExistsError(
            "Final direct model already exists. "
            f"Existing file preserved: {MODEL_FILE}"
        )

    df = load_training_data()

    model = train_model(df)

    artifact = save_model(
        model,
        df,
    )

    save_training_report(artifact)

    print("\nFINAL MODEL SUMMARY")

    print(
        f"Training examples: "
        f"{artifact['training_examples']:,}"
    )

    print(
        f"Forecast origins: "
        f"{artifact['training_origins']}"
    )

    print(
        f"Features: "
        f"{len(artifact['features'])}"
    )

    print(
        f"Maximum forecast horizon: "
        f"{artifact['maximum_horizon_hours']} hours"
    )

    print(
        "\nFINAL DIRECT MODEL TRAINING "
        "COMPLETED SUCCESSFULLY"
    )


if __name__ == "__main__":
    main()
