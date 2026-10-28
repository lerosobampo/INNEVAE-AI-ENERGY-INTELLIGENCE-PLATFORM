
"""
INNEVA.E — Historical Demand Forecast Performance Dashboard

Displays retrospective seven-day forecast backtests from the
multi-origin monitoring dataset.

This module does not retrain models, generate forecasts, or
modify the historical dataset.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FORECAST_HISTORY_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "multi_origin_monitoring"
    / "hourly_predictions.csv"
)

CANONICAL_HISTORY_PATH = (
    PROJECT_ROOT
    / "data"
    / "forecasting"
    / "energy_intelligence_hourly.csv"
)

REQUIRED_COLUMNS = {
    "issue_time_utc",
    "forecast_time_utc",
    "horizon",
    "selected_method",
    "step",
    "predicted_demand_mw",
    "actual_demand_mw",
}

METHOD_LABELS = {
    "recursive_ml": "Recursive ML",
    "weekly_naive": "Weekly Naïve",
}


@st.cache_data(ttl=300, show_spinner=False)
def load_forecast_history():
    """Read and validate the retrospective forecast dataset."""

    if not FORECAST_HISTORY_PATH.is_file():
        raise FileNotFoundError(
            f"Forecast history not found: {FORECAST_HISTORY_PATH}"
        )

    data = pd.read_csv(FORECAST_HISTORY_PATH)

    missing = REQUIRED_COLUMNS - set(data.columns)

    if missing:
        raise ValueError(
            f"Missing forecast-history columns: {sorted(missing)}"
        )

    if data.empty:
        raise ValueError("Forecast history is empty.")

    data = data.copy()

    for column in ["issue_time_utc", "forecast_time_utc"]:
        data[column] = pd.to_datetime(
            data[column],
            utc=True,
            format="ISO8601",
            errors="raise",
        )

    for column in [
        "step",
        "predicted_demand_mw",
        "actual_demand_mw",
    ]:
        data[column] = pd.to_numeric(
            data[column],
            errors="raise",
        )

    if data[list(REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError("Forecast history contains missing required values.")

    if not np.isfinite(
        data[["predicted_demand_mw", "actual_demand_mw"]]
        .to_numpy(dtype=float)
    ).all():
        raise ValueError("Forecast history contains non-finite values.")

    if (
        data[["predicted_demand_mw", "actual_demand_mw"]] <= 0
    ).any().any():
        raise ValueError("Forecast history contains non-positive demand.")

    if (data["step"] < 1).any():
        raise ValueError("Forecast steps must be positive.")

    if (data["step"] % 1 != 0).any():
        raise ValueError("Forecast steps must be whole numbers.")

    expected_targets = (
        data["issue_time_utc"]
        + pd.to_timedelta(data["step"] - 1, unit="h")
    )

    if not (data["forecast_time_utc"] == expected_targets).all():
        raise ValueError(
            "Forecast target timestamps do not match the step convention."
        )

    keys = [
        "issue_time_utc",
        "forecast_time_utc",
        "horizon",
        "selected_method",
    ]

    if data.duplicated(keys).any():
        raise ValueError("Duplicate forecast records detected.")

    # Cross-check recorded actuals against the canonical source.
    if not CANONICAL_HISTORY_PATH.is_file():
        raise FileNotFoundError(
            f"Canonical history not found: {CANONICAL_HISTORY_PATH}"
        )

    actuals = pd.read_csv(
        CANONICAL_HISTORY_PATH,
        usecols=["hour_start_utc", "actual_load_mw"],
    )

    actuals["hour_start_utc"] = pd.to_datetime(
        actuals["hour_start_utc"],
        utc=True,
        format="ISO8601",
        errors="raise",
    )

    if actuals["hour_start_utc"].duplicated().any():
        raise ValueError("Canonical history contains duplicate timestamps.")

    actuals["actual_load_mw"] = pd.to_numeric(
        actuals["actual_load_mw"],
        errors="raise",
    )

    actuals = actuals.rename(
        columns={
            "hour_start_utc": "forecast_time_utc",
            "actual_load_mw": "canonical_actual_mw",
        }
    )

    data = data.merge(
        actuals,
        on="forecast_time_utc",
        how="left",
        validate="many_to_one",
    )

    if data["canonical_actual_mw"].isna().any():
        raise ValueError(
            "Some forecast targets have no canonical actual demand."
        )

    differences = (
        data["actual_demand_mw"]
        - data["canonical_actual_mw"]
    ).abs()

    if (differences > 0.001).any():
        raise ValueError(
            "Forecast evaluation actuals disagree with canonical history."
        )

    data = data.drop(columns=["canonical_actual_mw"])

    return data.sort_values(
        ["issue_time_utc", "selected_method", "step"]
    ).reset_index(drop=True)


def prepare_forecasting_data(data):
    """Calculate consistent forecast-error fields."""

    result = data.copy()

    # Positive means actual demand exceeded the prediction.
    result["forecast_error_mw"] = (
        result["actual_demand_mw"]
        - result["predicted_demand_mw"]
    )

    result["absolute_error_mw"] = (
        result["forecast_error_mw"].abs()
    )

    result["squared_error"] = (
        result["forecast_error_mw"] ** 2
    )

    result["absolute_percentage_error"] = (
        100
        * result["absolute_error_mw"]
        / result["actual_demand_mw"].abs()
    )

    result["date_utc"] = (
        result["forecast_time_utc"].dt.date
    )

    return result


def calculate_forecast_metrics(data):
    """Calculate metrics for one selected forecasting method."""

    if data.empty:
        return None

    return {
        "mae_mw": float(data["absolute_error_mw"].mean()),
        "rmse_mw": float(
            np.sqrt(data["squared_error"].mean())
        ),
        "mape_pct": float(
            data["absolute_percentage_error"].mean()
        ),
        "mean_error_mw": float(
            data["forecast_error_mw"].mean()
        ),
        "observations": len(data),
    }


def render_forecasting_dashboard():
    """Render validated retrospective forecast performance."""

    st.header("Historical Demand Forecast Performance")

    st.info(
        "Retrospective historical backtesting using stored "
        "seven-day forecast predictions. These results are "
        "not live forecasts or evidence of operational "
        "forecast accuracy."
    )

    try:
        raw_data = load_forecast_history()
        data = prepare_forecasting_data(raw_data)

    except Exception as error:
        st.error(
            f"Unable to load historical forecast performance: {error}"
        )
        return

    horizons = sorted(data["horizon"].unique().tolist())

    if horizons != ["7d"]:
        st.warning(
            "The source contains forecast horizons other than "
            "the validated seven-day monitoring dataset. "
            "Check the source before interpreting results."
        )
        return

    methods = sorted(data["selected_method"].unique().tolist())

    selected_method = st.selectbox(
        "Forecasting method",
        options=methods,
        format_func=lambda method: METHOD_LABELS.get(
            method, method
        ),
        key="historical_forecast_method",
    )

    method_data = data.loc[
        data["selected_method"] == selected_method
    ].copy()

    if method_data.empty:
        st.warning("No forecasts available for this method.")
        return

    min_date = method_data["date_utc"].min()
    max_date = method_data["date_utc"].max()

    selected_dates = st.date_input(
        "Select forecasting analysis period",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="historical_forecast_date_range",
    )

    if (
        not isinstance(selected_dates, (tuple, list))
        or len(selected_dates) != 2
    ):
        st.warning("Select both a start and end date.")
        return

    start_date, end_date = selected_dates

    if start_date > end_date:
        st.warning("The start date must not exceed the end date.")
        return

    filtered = method_data.loc[
        (method_data["date_utc"] >= start_date)
        & (method_data["date_utc"] <= end_date)
    ].copy()

    if filtered.empty:
        st.warning("No observations in the selected period.")
        return

    origin_count = filtered["issue_time_utc"].nunique()

    st.caption(
        f"Method: {METHOD_LABELS.get(selected_method, selected_method)} "
        f"| Horizon: 7 days "
        f"| Forecast origins represented: {origin_count} "
        f"| Target period: {start_date} to {end_date} (UTC)"
    )

    metrics = calculate_forecast_metrics(filtered)

    st.subheader("Historical Forecast Performance")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Mean Absolute Error",
            f"{metrics['mae_mw']:,.2f} MW",
        )

    with col2:
        st.metric(
            "Root Mean Squared Error",
            f"{metrics['rmse_mw']:,.2f} MW",
        )

    with col3:
        st.metric(
            "Mean Absolute Percentage Error",
            f"{metrics['mape_pct']:,.2f}%",
        )

    with col4:
        st.metric(
            "Evaluated Predictions",
            f"{metrics['observations']:,}",
        )

    st.caption(
        "Metrics are calculated from the selected method's "
        "stored predictions and canonical actual demand. "
        "These are not the separate persistence forecast's metrics."
    )

    st.divider()

    st.subheader("Actual vs Historical Forecast Demand")

    comparison = filtered[
        [
            "forecast_time_utc",
            "actual_demand_mw",
            "predicted_demand_mw",
        ]
    ].rename(
        columns={
            "actual_demand_mw": "Actual Demand",
            "predicted_demand_mw": "Historical Forecast",
        }
    )

    comparison_long = comparison.melt(
        id_vars="forecast_time_utc",
        var_name="Series",
        value_name="Demand (MW)",
    )

    comparison_figure = px.line(
        comparison_long,
        x="forecast_time_utc",
        y="Demand (MW)",
        color="Series",
        title="Hourly Actual vs Historical Forecast",
        labels={
            "forecast_time_utc": "Forecast Target (UTC)",
        },
    )

    comparison_figure.update_layout(hovermode="x unified")

    st.plotly_chart(
        comparison_figure,
        use_container_width=True,
    )

    st.divider()

    st.subheader("Forecast Error Analysis")

    error_figure = px.line(
        filtered,
        x="forecast_time_utc",
        y="forecast_error_mw",
        title="Hourly Forecast Error",
        labels={
            "forecast_time_utc": "Forecast Target (UTC)",
            "forecast_error_mw": "Actual - Forecast (MW)",
        },
    )

    error_figure.add_hline(
        y=0,
        line_dash="dash",
    )

    st.plotly_chart(
        error_figure,
        use_container_width=True,
    )

    st.caption(
        "Positive errors indicate underprediction. "
        "Negative errors indicate overprediction."
    )

    st.divider()

    st.subheader("Daily Forecast Performance")

    daily_performance = (
        filtered.groupby("date_utc", as_index=False)
        .agg(
            mae_mw=("absolute_error_mw", "mean"),
            rmse_squared=("squared_error", "mean"),
            mape_pct=("absolute_percentage_error", "mean"),
            observations=("absolute_error_mw", "size"),
        )
    )

    daily_performance["rmse_mw"] = np.sqrt(
        daily_performance["rmse_squared"]
    )

    daily_performance = daily_performance.drop(
        columns=["rmse_squared"]
    )

    daily_figure = px.bar(
        daily_performance,
        x="date_utc",
        y="mae_mw",
        title="Daily Mean Absolute Error",
        labels={
            "date_utc": "Date (UTC)",
            "mae_mw": "MAE (MW)",
        },
    )

    st.plotly_chart(
        daily_figure,
        use_container_width=True,
    )

    with st.expander("View Forecasting Dataset"):
        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True,
        )

    st.download_button(
        "Download Forecast Analysis (CSV)",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="innevae_historical_forecast_analysis.csv",
        mime="text/csv",
        key="download_historical_forecast_analysis",
    )

    st.warning(
        "These predictions were generated retrospectively "
        "using historical evaluation periods. The source "
        "script restricts forecast inputs to observations "
        "before the issue timestamp, but this dashboard "
        "does not independently certify the model-training "
        "pipeline or establish live forecasting performance."
    )
