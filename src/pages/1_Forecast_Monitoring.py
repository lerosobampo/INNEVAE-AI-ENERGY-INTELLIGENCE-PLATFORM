
"""
INNEVA.E — Forecast Monitoring Dashboard
Module 17.7D.1

Read-only Streamlit dashboard showing:
- Forecast registry coverage
- Evaluated forecast accuracy
- Recursive ML vs weekly naive
- Weekly forecast consistency
- Lead-time accuracy
- Reliability assessment

All data is loaded from existing CSV reports.
No forecasts are generated and no databases are modified.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[3]

EVALUATION_DIR = (
    PROJECT_ROOT / "data/processed/forecast_evaluation"
)

MONITORING_DIR = (
    PROJECT_ROOT / "data/processed/multi_origin_monitoring"
)

RELIABILITY_DIR = (
    PROJECT_ROOT / "data/processed/forecast_reliability"
)


st.set_page_config(
    page_title="INNEVA.E | Forecast Monitoring",
    page_icon="📈",
    layout="wide",
)


@st.cache_data
def read_csv(path):
    if not path.exists():
        return None
    return pd.read_csv(path)


def require_report(path, label):
    data = read_csv(path)

    if data is None or data.empty:
        st.error(
            f"Missing or empty report: {label}\n\n"
            f"Expected location: `{path}`"
        )
        st.stop()

    return data


def metric_value(value, decimals=2, suffix=""):
    if pd.isna(value):
        return "N/A"

    return f"{value:,.{decimals}f}{suffix}"


def main():
    st.title("INNEVA.E — Forecast Monitoring")

    st.caption(
        "Historical forecasting accuracy, model comparisons, "
        "and reliability assessment."
    )

    st.info(
        "These results are retrospective development-period "
        "diagnostics. They are not validated estimates of "
        "future operational forecasting performance."
    )

    evaluated = require_report(
        EVALUATION_DIR / "registered_predictions_evaluated.csv",
        "Registered forecast evaluation",
    )

    run_summary = require_report(
        EVALUATION_DIR / "registered_forecast_summary.csv",
        "Registered forecast summary",
    )

    overall = require_report(
        MONITORING_DIR / "overall_performance.csv",
        "Multi-origin overall performance",
    )

    lead = require_report(
        MONITORING_DIR / "lead_time_performance.csv",
        "Multi-origin lead-time performance",
    )

    comparison = require_report(
        MONITORING_DIR / "origin_comparison.csv",
        "Multi-origin comparison",
    )

    reliability = require_report(
        RELIABILITY_DIR / "reliability_summary.csv",
        "Reliability assessment",
    )

    weekly = require_report(
        RELIABILITY_DIR / "weekly_reliability.csv",
        "Weekly reliability",
    )

    decision = reliability.iloc[0]

    st.divider()

    st.subheader("1. Forecast Registry Coverage")

    evaluated_count = int(
        (evaluated["evaluation_status"] == "evaluated").sum()
    )

    pending_count = int(
        (evaluated["evaluation_status"] == "pending_actual").sum()
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Registered Forecasts",
        len(run_summary),
    )

    col2.metric(
        "Stored Predictions",
        len(evaluated),
    )

    col3.metric(
        "Evaluated Hours",
        evaluated_count,
    )

    col4.metric(
        "Pending Actuals",
        pending_count,
    )

    st.caption(
        "Registry coverage is separate from the eight-origin "
        "benchmark evaluation below."
    )

    with st.expander("Registered forecast details"):
        columns = [
            "forecast_id",
            "issue_time_utc",
            "horizon",
            "selected_method",
            "forecast_origin_type",
            "evaluated_count",
            "pending_count",
            "mae_mw",
            "mape_pct",
        ]

        available = [
            column
            for column in columns
            if column in run_summary.columns
        ]

        st.dataframe(
            run_summary[available],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    st.subheader("2. Model Accuracy Comparison")

    ml_row = overall.loc[
        overall["evaluation_method"] == "recursive_ml"
    ]

    baseline_row = overall.loc[
        overall["evaluation_method"] == "weekly_naive"
    ]

    if ml_row.empty or baseline_row.empty:
        st.error(
            "Both recursive_ml and weekly_naive "
            "are required for comparison."
        )
        st.stop()

    ml = ml_row.iloc[0]
    baseline = baseline_row.iloc[0]

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Recursive ML MAE",
        metric_value(ml["mae_mw"], suffix=" MW"),
    )

    col2.metric(
        "Weekly Naive MAE",
        metric_value(baseline["mae_mw"], suffix=" MW"),
    )

    col3.metric(
        "ML MAE Improvement",
        metric_value(
            decision["overall_ml_improvement_pct"],
            suffix="%",
        ),
    )

    metric_columns = [
        "evaluation_method",
        "hours",
        "mae_mw",
        "rmse_mw",
        "mape_pct",
        "bias_mw",
    ]

    st.dataframe(
        overall[metric_columns],
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "Lower MAE, RMSE and MAPE indicate better accuracy. "
        "Bias is signed: positive means overprediction."
    )

    st.divider()

    st.subheader("3. Accuracy by Forecast Lead Time")

    lead_chart = lead.pivot(
        index="lead_bucket",
        columns="evaluation_method",
        values="mae_mw",
    )

    bucket_order = [
        "01-24h",
        "25-72h",
        "73-168h",
    ]

    lead_chart = lead_chart.reindex(
        [
            bucket
            for bucket in bucket_order
            if bucket in lead_chart.index
        ]
    )

    st.line_chart(
        lead_chart,
        x_label="Forecast lead time",
        y_label="Mean absolute error (MW)",
    )

    st.dataframe(
        lead[
            [
                "evaluation_method",
                "lead_bucket",
                "hours",
                "mae_mw",
                "mape_pct",
                "bias_mw",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("4. Weekly Model Consistency")

    comparison = comparison.copy()

    comparison["evaluation_origin_utc"] = pd.to_datetime(
        comparison["evaluation_origin_utc"],
        utc=True,
    )

    comparison = comparison.sort_values(
        "evaluation_origin_utc"
    )

    weekly_chart = comparison.set_index(
        "evaluation_origin_utc"
    )[
        [
            "recursive_ml",
            "weekly_naive",
        ]
    ]

    st.line_chart(
        weekly_chart,
        x_label="Forecast issue date",
        y_label="Seven-day MAE (MW)",
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "ML Weekly Wins",
        int(decision["ml_wins"]),
    )

    col2.metric(
        "Baseline Weekly Wins",
        int(decision["baseline_wins"]),
    )

    col3.metric(
        "ML Win Rate",
        metric_value(
            decision["ml_win_rate_pct"],
            decimals=1,
            suffix="%",
        ),
    )

    st.dataframe(
        weekly,
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("5. Forecast Reliability Assessment")

    status = str(
        decision["reliability_status"]
    )

    if status == "limited_evidence":
        st.warning(
            "Model reliability: Limited evidence. "
            "Recursive ML has a small average advantage, "
            "but its performance is not consistently superior."
        )
    else:
        st.info(
            f"Reliability status: {status}"
        )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Reliability Checks",
        (
            f"{int(decision['checks_passed'])}/"
            f"{int(decision['checks_total'])}"
        ),
    )

    col2.metric(
        "Worst Weekly ML Improvement",
        metric_value(
            decision["worst_weekly_improvement_pct"],
            suffix="%",
        ),
    )

    col3.metric(
        "Forecast Origins",
        int(decision["forecast_origins"]),
    )

    check_columns = [
        column
        for column in reliability.columns
        if column.startswith("check_")
    ]

    checks = pd.DataFrame(
        {
            "Criterion": [
                column.replace("check_", "").replace("_", " ")
                for column in check_columns
            ],
            "Passed": [
                bool(decision[column])
                for column in check_columns
            ],
        }
    )

    st.dataframe(
        checks,
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("**Current recommendation**")

    recommendation = str(
        decision["recommendation"]
    )

    if recommendation == "retain_provisional_default_and_monitor":
        st.write(
            "Keep recursive ML as the provisional seven-day "
            "default. Continue benchmarking against weekly "
            "naive. Do not enable automatic model switching "
            "based on these results alone."
        )
    else:
        st.write(
            recommendation.replace("_", " ").capitalize()
        )

    st.caption(
        "Reliability thresholds are provisional engineering "
        "criteria, not statistical guarantees. The evaluation "
        "period was previously inspected during development."
    )

    st.divider()

    st.subheader("6. Export Monitoring Reports")

    csv_data = weekly.to_csv(index=False)

    st.download_button(
        "Download Weekly Reliability Report",
        data=csv_data,
        file_name="innevae_weekly_reliability.csv",
        mime="text/csv",
    )

    st.success(
        "Forecast monitoring reports loaded successfully."
    )


if __name__ == "__main__":
    main()
