"""
INNEVA.E - ENERGY INTELLIGENCE PLATFORM

Interactive Streamlit dashboard.

Features:
- Historical energy KPIs
- Demand forecasting
- AI intelligence
- Dynamic AI analyst
- Automation monitoring
- System monitoring
- Data quality monitoring
- Forecast monitoring
"""

from datetime import date, timedelta
from pathlib import Path
from PIL import Image
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

from energy_overview_90d import render_energy_overview
from forecasting_dashboard import render_forecasting_dashboard
from persistence_forecast import render_persistence_forecast
from ai_intelligence_dashboard import render_ai_intelligence_dashboard
from dynamic_agent_dashboard import render_dynamic_agent_dashboard
from automation_monitoring_dashboard import render_automation_monitoring_dashboard
from system_monitoring_dashboard import render_system_monitoring_dashboard
from data_quality_dashboard import render_data_quality_dashboard
from automated_forecasting_dashboard import render_automated_forecasting_dashboard
from branding import apply_branding


# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="INNEVA.E | Energy Intelligence",
    page_icon=Image.open(Path(__file__).resolve().parents[2] / "assets" / "innevae_favicon.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==========================================
# CANONICAL DATA LOADING
# ==========================================

forecasting_path = Path(__file__).resolve().parents[1] / "forecasting"

if str(forecasting_path) not in sys.path:
    sys.path.insert(0, str(forecasting_path))

from unified_data_loader import load_energy_history


@st.cache_data(ttl=300)
def get_canonical_energy_data(mode):
    return load_energy_history(mode=mode)




# ==========================================
# SIDEBAR
# ==========================================

apply_branding()

st.sidebar.divider()

# Flat, individually styled sidebar navigation (no radio-button circles).
# Streamlit Material icons are monochrome SVG glyphs, not emoji.
NAVIGATION_ITEMS = [
    ("Dynamic AI Analyst", "smart_toy", "dynamic_ai"),
    ("Energy Overview", "bolt", "energy_overview"),
    ("Demand Forecasting", "trending_up", "demand_forecasting"),
    ("Automated Forecasting", "autorenew", "automated_forecasting"),
    ("AI Intelligence", "psychology", "ai_intelligence"),
    ("Automation Monitoring", "settings", "automation_monitoring"),
    ("System Monitoring", "desktop_windows", "system_monitoring"),
    ("Data Quality Monitoring", "verified_user", "data_quality_monitoring"),
    ("Forecast Monitoring", "bar_chart", "forecast_monitoring"),
]

if st.session_state.get("innevae_selected_page") not in {
    item[0] for item in NAVIGATION_ITEMS
}:
    st.session_state["innevae_selected_page"] = "Dynamic AI Analyst"

# Override the global green button styling for navigation buttons only.
# The keys create stable Streamlit container classes for each item.
selected_key = next(
    item[2] for item in NAVIGATION_ITEMS
    if item[0] == st.session_state["innevae_selected_page"]
)
st.sidebar.markdown(
    """
    <style>
    [data-testid="stSidebar"] [class*="st-key-innevae_nav_"] button {
        width: 100% !important;
        justify-content: flex-start !important;
        gap: 0.65rem !important;
        background: transparent !important;
        border: 0 !important;
        box-shadow: none !important;
        border-radius: 8px !important;
        color: #ffffff !important;
        text-align: left !important;
        padding: 0.55rem 0.7rem !important;
        min-height: 2.55rem !important;
    }
    [data-testid="stSidebar"] [class*="st-key-innevae_nav_"] button:hover {
        background: #17643A !important;
    }
    [data-testid="stSidebar"] [class*="st-key-innevae_nav_"] button p {
        color: #ffffff !important;
        font-weight: 500 !important;
    }
    [data-testid="stSidebar"] [class*="st-key-innevae_nav_"] button [data-testid="stIconMaterial"] {
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] [class*="st-key-innevae_nav_"] button span.material-symbols-rounded {
        color: #ffffff !important;
    }
    [data-testid="stSidebar"] .st-key-innevae_nav_""" + selected_key + """ button {
        background: #17643A !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown("**Navigation**")
for label, icon_name, nav_key in NAVIGATION_ITEMS:
    if st.sidebar.button(
        label,
        key=f"innevae_nav_{nav_key}",
        icon=f":material/{icon_name}:",
        use_container_width=True,
    ):
        st.session_state["innevae_selected_page"] = label
        st.rerun()

page = st.session_state["innevae_selected_page"]

st.sidebar.divider()

st.sidebar.caption(
    "Environment: Local Development"
)

st.sidebar.caption(
    "Dynamic AI Model: Qwen2.5 3B"
)

st.sidebar.caption(
    "Data source: Historical SQLite"
)


# ==========================================
# MAIN HEADER
# ==========================================

st.title("INNEVA.E")

st.subheader(
    "AI Energy Intelligence Platform"
)

st.caption(
    "Historical energy analytics, demand forecasting, "
    "local AI interpretation, and automation monitoring."
)

st.divider()


# ==========================================
# ENERGY OVERVIEW
# ==========================================

if page == "Energy Overview":

    mode = st.radio(
        "Historical dataset",
        ["development_90d", "full_history"],
        horizontal=True,
        format_func=lambda x: (
            "Latest 90 days"
            if x == "development_90d"
            else "Full history (2024 onward)"
        ),
    )

    try:
        energy_history = get_canonical_energy_data(mode)
        render_energy_overview(energy_history)

    except Exception as error:
        st.error(
            f"Unable to load canonical historical data: {error}"
        )


# ==========================================
# DEMAND FORECASTING
# ==========================================

elif page == "Demand Forecasting":

    render_persistence_forecast()

    st.divider()

    render_forecasting_dashboard()

    st.divider()

    st.header("Historical Demand Forecast Engine")

    st.caption(
        "Experimental hourly forecasts using the historical dataset. "
        "Not live data or a production-certified prediction service."
    )

    forecasting_path = (
        Path(__file__).resolve().parents[1] / "forecasting"
    )

    if str(forecasting_path) not in sys.path:
        sys.path.insert(0, str(forecasting_path))

    try:
        from unified_forecast_engine import forecast, AUTO_METHODS
        from one_hour_forecast import load_historical_data

    except ImportError as error:
        st.error(
            f"Unable to import the unified forecasting engine: {error}"
        )
        st.stop()

    @st.cache_data(show_spinner=False)
    def get_forecasting_history():
        return load_historical_data()

    try:
        forecast_history = get_forecasting_history()

        latest_observation = pd.to_datetime(
            forecast_history["hour_start_utc"],
            utc=True,
        ).max()

        earliest_observation = pd.to_datetime(
            forecast_history["hour_start_utc"],
            utc=True,
        ).min()

    except (ValueError, KeyError, OSError) as error:
        st.error(
            f"Unable to load forecasting history: {error}"
        )
        st.stop()

    latest_issue = (
        latest_observation + pd.Timedelta(hours=1)
    )

    earliest_issue = (
        earliest_observation + pd.Timedelta(hours=168)
    )

    st.info(
        f"Historical observations available through "
        f"{latest_observation:%Y-%m-%d %H:%M} UTC. "
        "The selected issue time requires 168 preceding "
        "observed hours. ML model training cutoffs may "
        "further restrict earlier issue dates."
    )

    with st.form("unified_forecast_form"):

        date_col, hour_col = st.columns(2)

        with date_col:
            issue_date = st.date_input(
                "Forecast issue date (UTC)",
                value=latest_issue.date(),
                min_value=earliest_issue.date(),
                max_value=latest_issue.date(),
            )

        with hour_col:
            issue_hour = st.selectbox(
                "Issue hour (UTC)",
                options=list(range(24)),
                index=int(latest_issue.hour),
                format_func=lambda hour: f"{hour:02d}:00",
            )

        horizon_col, method_col = st.columns(2)

        with horizon_col:
            selected_horizon = st.selectbox(
                "Forecast horizon",
                options=["1h", "24h", "7d", "30d"],
                index=1,
                format_func=lambda value: {
                    "1h": "1 hour",
                    "24h": "24 hours",
                    "7d": "7 days",
                    "30d": "30 days",
                }[value],
            )

        with method_col:
            selected_method = st.selectbox(
                "Forecasting method",
                options=[
                    "auto",
                    "recursive_ml",
                    "direct_ml",
                    "daily_naive",
                    "weekly_naive",
                ],
                format_func=lambda value: {
                    "auto": "Automatic (recommended candidate)",
                    "recursive_ml": "Recursive ML",
                    "direct_ml": "Direct ML",
                    "daily_naive": "Daily seasonal naive",
                    "weekly_naive": "Weekly seasonal naive",
                }[value],
            )

        submitted = st.form_submit_button(
            "Generate Forecast",
            type="primary",
        )

    if submitted:

        issue_timestamp = pd.Timestamp(
            f"{issue_date.isoformat()}"
            f"T{issue_hour:02d}:00:00+00:00"
        )

        if issue_timestamp > latest_issue:

            st.error(
                "This issue time is later than the last "
                "supported historical issue. "
                "Live observations are not connected."
            )

            st.session_state.pop(
                "unified_forecast_result",
                None,
            )

        elif issue_timestamp < earliest_issue:

            st.error(
                "At least 168 preceding hours are required."
            )

            st.session_state.pop(
                "unified_forecast_result",
                None,
            )

        else:

            try:
                with st.spinner(
                    "Generating hourly forecast..."
                ):

                    result = forecast(
                        issue_time=issue_timestamp,
                        horizon=selected_horizon,
                        method=selected_method,
                        historical_data=forecast_history,
                    )

                st.session_state[
                    "unified_forecast_result"
                ] = result

            except (
                ValueError,
                KeyError,
                FileNotFoundError,
                RuntimeError,
            ) as error:

                st.error(
                    f"Forecast could not be generated: {error}"
                )

                st.session_state.pop(
                    "unified_forecast_result",
                    None,
                )

    result = st.session_state.get(
        "unified_forecast_result"
    )

    if result is not None and not result.empty:

        result_issue = pd.Timestamp(
            result["issue_time_utc"].iloc[0]
        )

        actual_method = result[
            "selected_method"
        ].iloc[0]

        actual_horizon = result[
            "horizon"
        ].iloc[0]

        st.success(
            f"{actual_horizon} forecast generated "
            f"using {actual_method}. "
            f"Issue: {result_issue:%Y-%m-%d %H:%M} UTC."
        )

        predictions = result[
            "predicted_demand_mw"
        ]

        metric_a, metric_b, metric_c, metric_d = (
            st.columns(4)
        )

        metric_a.metric(
            "Average demand",
            f"{predictions.mean():,.0f} MW",
        )

        metric_b.metric(
            "Minimum demand",
            f"{predictions.min():,.0f} MW",
        )

        metric_c.metric(
            "Maximum demand",
            f"{predictions.max():,.0f} MW",
        )

        metric_d.metric(
            "Forecast hours",
            f"{len(result):,}",
        )

        chart = px.line(
            result,
            x="forecast_time_utc",
            y="predicted_demand_mw",
            labels={
                "forecast_time_utc": "Forecast time (UTC)",
                "predicted_demand_mw": "Predicted demand (MW)",
            },
            title="Hourly Electricity Demand Forecast",
        )

        chart.update_layout(
            hovermode="x unified"
        )

        st.plotly_chart(
            chart,
            use_container_width=True,
        )

        with st.expander(
            "Hourly forecast predictions"
        ):

            st.dataframe(
                result,
                use_container_width=True,
                hide_index=True,
            )

        st.download_button(
            "Download Forecast (CSV)",
            data=result.to_csv(
                index=False
            ).encode("utf-8"),
            file_name=(
                f"innevae_forecast_"
                f"{actual_horizon}_"
                f"{actual_method}_"
                f"{result_issue:%Y%m%d_%H%M}_utc.csv"
            ),
            mime="text/csv",
        )

    st.caption(
        "Method selection is provisional. "
        "The demand measurement definition and "
        "publication delay have not yet been verified. "
        "Historical observations are assumed available "
        "immediately after each hourly interval, "
        "which may not hold operationally."
    )


# ==========================================
# AI INTELLIGENCE
# ==========================================

elif page == "Automated Forecasting":

    render_automated_forecasting_dashboard()


elif page == "AI Intelligence":

    render_ai_intelligence_dashboard()


# ==========================================
# DYNAMIC AI ANALYST
# ==========================================

elif page == "Dynamic AI Analyst":

    render_dynamic_agent_dashboard()


# ==========================================
# AUTOMATION MONITORING
# ==========================================

elif page == "Automation Monitoring":

    render_automation_monitoring_dashboard()


# ==========================================
# SYSTEM MONITORING
# ==========================================

elif page == "System Monitoring":

    render_system_monitoring_dashboard()


# ==========================================
# DATA QUALITY MONITORING (MODULE 20.4)
# ==========================================

elif page == "Data Quality Monitoring":

    render_data_quality_dashboard()


# ==========================================
# FORECAST MONITORING
# ==========================================

elif page == "Forecast Monitoring":

    st.header("Forecast Monitoring")

    st.caption(
        "Registered forecast evaluation, "
        "benchmark comparison, and model reliability."
    )

    st.info(
        "These are retrospective development-period "
        "diagnostics, not a validated estimate of "
        "future operational performance."
    )

    project_root = (
        Path(__file__).resolve().parents[2]
    )

    evaluation_dir = (
        project_root
        / "data/processed/forecast_evaluation"
    )

    multi_dir = (
        project_root
        / "data/processed/multi_origin_monitoring"
    )

    reliability_dir = (
        project_root
        / "data/processed/forecast_reliability"
    )

    @st.cache_data(
        ttl=30,
        show_spinner=False,
    )
    def load_monitoring_csv(path_string):

        path = Path(path_string)

        if not path.is_file():
            return None

        return pd.read_csv(path)

    def monitoring_report(directory, filename):

        path = directory / filename

        df = load_monitoring_csv(str(path))

        if df is None or df.empty:

            st.error(
                f"Missing or empty monitoring report: `{path}`"
            )

            st.caption(
                "Run the corresponding forecasting "
                "evaluation script first."
            )

            st.stop()

        return df

    evaluated = monitoring_report(
        evaluation_dir,
        "registered_predictions_evaluated.csv",
    )

    registered = monitoring_report(
        evaluation_dir,
        "registered_forecast_summary.csv",
    )

    overall = monitoring_report(
        multi_dir,
        "overall_performance.csv",
    )

    lead = monitoring_report(
        multi_dir,
        "lead_time_performance.csv",
    )

    comparison = monitoring_report(
        multi_dir,
        "origin_comparison.csv",
    )

    reliability = monitoring_report(
        reliability_dir,
        "reliability_summary.csv",
    )

    weekly = monitoring_report(
        reliability_dir,
        "weekly_reliability.csv",
    )

    decision = reliability.iloc[0]

    st.subheader(
        "1. Forecast Registry Coverage"
    )

    evaluated_hours = int(
        (
            evaluated["evaluation_status"]
            == "evaluated"
        ).sum()
    )

    pending_hours = int(
        (
            evaluated["evaluation_status"]
            == "pending_actual"
        ).sum()
    )

    m1, m2, m3, m4 = st.columns(4)

    m1.metric(
        "Registered forecasts",
        f"{len(registered):,}",
    )

    m2.metric(
        "Stored predictions",
        f"{len(evaluated):,}",
    )

    m3.metric(
        "Evaluated hours",
        f"{evaluated_hours:,}",
    )

    m4.metric(
        "Pending actuals",
        f"{pending_hours:,}",
    )

    st.caption(
        "Registry coverage is separate from "
        "the multi-origin benchmark experiment."
    )

    with st.expander(
        "Registered forecast details"
    ):

        fields = [
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

        st.dataframe(
            registered[
                [
                    c for c in fields
                    if c in registered.columns
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    st.subheader(
        "2. Model vs. Benchmark"
    )

    methods = overall.set_index(
        "evaluation_method"
    )

    if not {
        "recursive_ml",
        "weekly_naive",
    }.issubset(methods.index):

        st.error(
            "Missing recursive ML or weekly naive comparison."
        )

        st.stop()

    ml = methods.loc["recursive_ml"]
    baseline = methods.loc["weekly_naive"]

    m1, m2, m3 = st.columns(3)

    m1.metric(
        "Recursive ML MAE",
        f"{ml['mae_mw']:,.2f} MW",
    )

    m2.metric(
        "Weekly naive MAE",
        f"{baseline['mae_mw']:,.2f} MW",
    )

    m3.metric(
        "ML improvement",
        f"{decision['overall_ml_improvement_pct']:.2f}%",
    )

    st.dataframe(
        overall,
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader(
        "3. Accuracy by Forecast Lead Time"
    )

    lead_plot = lead.pivot(
        index="lead_bucket",
        columns="evaluation_method",
        values="mae_mw",
    )

    lead_order = [
        "01-24h",
        "25-72h",
        "73-168h",
    ]

    lead_plot = lead_plot.reindex(
        [
            x for x in lead_order
            if x in lead_plot.index
        ]
    )

    st.line_chart(lead_plot)

    st.caption(
        "Mean absolute error (MW). Lower is better."
    )

    st.dataframe(
        lead,
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader(
        "4. Weekly Model Consistency"
    )

    comparison = comparison.copy()

    comparison[
        "evaluation_origin_utc"
    ] = pd.to_datetime(
        comparison["evaluation_origin_utc"],
        utc=True,
    )

    comparison = comparison.sort_values(
        "evaluation_origin_utc"
    )

    st.line_chart(
        comparison.set_index(
            "evaluation_origin_utc"
        )[
            [
                "recursive_ml",
                "weekly_naive",
            ]
        ]
    )

    m1, m2, m3 = st.columns(3)

    m1.metric(
        "ML wins",
        int(decision["ml_wins"]),
    )

    m2.metric(
        "Baseline wins",
        int(decision["baseline_wins"]),
    )

    m3.metric(
        "ML win rate",
        f"{decision['ml_win_rate_pct']:.1f}%",
    )

    st.dataframe(
        weekly,
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader(
        "5. Forecast Reliability"
    )

    status = str(
        decision["reliability_status"]
    )

    if status == "limited_evidence":

        st.warning(
            "Limited evidence: recursive ML has a "
            "small average accuracy advantage, "
            "but it does not consistently outperform "
            "weekly naive."
        )

    else:

        st.info(
            f"Reliability status: "
            f"{status.replace('_', ' ')}"
        )

    m1, m2, m3 = st.columns(3)

    m1.metric(
        "Checks passed",
        f"{int(decision['checks_passed'])}/"
        f"{int(decision['checks_total'])}",
    )

    m2.metric(
        "Worst weekly ML improvement",
        f"{decision['worst_weekly_improvement_pct']:.2f}%",
    )

    m3.metric(
        "Forecast origins",
        int(decision["forecast_origins"]),
    )

    check_columns = [
        c for c in reliability.columns
        if c.startswith("check_")
    ]

    if check_columns:

        check_table = pd.DataFrame(
            {
                "Criterion": [
                    c.removeprefix(
                        "check_"
                    ).replace("_", " ")
                    for c in check_columns
                ],
                "Passed": [
                    str(
                        decision[c]
                    ).strip().lower() == "true"
                    for c in check_columns
                ],
            }
        )

        st.dataframe(
            check_table,
            use_container_width=True,
            hide_index=True,
        )

    if (
        decision["recommendation"]
        == "retain_provisional_default_and_monitor"
    ):

        st.write(
            "**Recommendation:** Keep recursive ML "
            "as the provisional seven-day default. "
            "Continue benchmarking against weekly naive; "
            "do not automatically switch models "
            "on this evidence alone."
        )

    else:

        st.write(
            "**Recommendation:**",
            str(
                decision["recommendation"]
            ).replace("_", " "),
        )

    st.caption(
        "Decision thresholds are provisional heuristics; "
        "the evaluation period was previously inspected."
    )

    st.download_button(
        "Download weekly reliability report (CSV)",
        data=weekly.to_csv(
            index=False
        ).encode("utf-8"),
        file_name="innevae_weekly_reliability.csv",
        mime="text/csv",
    )


# ==========================================
# DEVELOPMENT INFORMATION
# ==========================================

# Legacy SQLite database retained for compatibility.
# This is separate from the forecasting registry.
DATABASE_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "database"
    / "innevae_energy.db"
)

st.divider()

with st.expander(
    "Development Environment"
):

    st.write(
        "Canonical energy dataset:",
        "data/forecasting/energy_intelligence_hourly.csv",
    )

    st.write(
        "Development period:",
        "Latest 90 complete UTC days",
    )

    st.write(
        "Legacy SQLite database "
        "(retained for compatibility):",
        str(DATABASE_PATH),
    )

    st.write(
        "Legacy SQLite database exists:",
        DATABASE_PATH.is_file(),
    )

    st.write(
        "Forecast registry and monitoring reports "
        "remain unchanged."
    )

st.caption(
    "INNEVA.E | Local Development | "
    "Canonical 90-day energy overview"
)