
import sqlite3
from pathlib import Path

# Locate the SQLite database
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT / "data" / "database" / "innevae_platform.db"
)


def analyze_demand():

    with sqlite3.connect(DATABASE_PATH) as connection:

        # QUERY 1: Basic demand statistics
        print("\n--- ELECTRICITY DEMAND SUMMARY ---")

        query_1 = """
            SELECT
                COUNT(*) AS total_hours,
                ROUND(AVG(actual_total_load_mw), 2) AS avg_demand_mw,
                ROUND(MIN(actual_total_load_mw), 2) AS min_demand_mw,
                ROUND(MAX(actual_total_load_mw), 2) AS max_demand_mw
            FROM electricity_demand;
        """

        result = connection.execute(query_1).fetchone()

        print(f"Total hours: {result[0]}")
        print(f"Average demand: {result[1]} MW")
        print(f"Minimum demand: {result[2]} MW")
        print(f"Maximum demand: {result[3]} MW")

        # QUERY 2: Five highest-demand hours
        print("\n--- TOP 5 PEAK DEMAND HOURS ---")

        query_2 = """
            SELECT
                interval_start_utc,
                ROUND(actual_total_load_mw, 2)
            FROM electricity_demand
            WHERE actual_total_load_mw IS NOT NULL
            ORDER BY actual_total_load_mw DESC
            LIMIT 5;
        """

        for timestamp, demand in connection.execute(query_2):
            print(f"{timestamp}: {demand} MW")

        # QUERY 3: Forecast accuracy
        print("\n--- DAY-AHEAD FORECAST ACCURACY ---")

        query_3 = """
            SELECT
                COUNT(*) AS paired_hours,
                ROUND(AVG(
                    ABS(
                        actual_total_load_mw
                        - day_ahead_total_load_forecast_mw
                    )
                ), 2) AS mae_mw
            FROM electricity_demand
            WHERE actual_total_load_mw IS NOT NULL
              AND day_ahead_total_load_forecast_mw IS NOT NULL;
        """

        paired_hours, mae = connection.execute(query_3).fetchone()

        print(f"Hours with actual and forecast values: {paired_hours}")
        print(f"Mean Absolute Error (MAE): {mae} MW")

        # QUERY 4: Forecast quality diagnostics
        print("\n--- FORECAST QUALITY DIAGNOSTICS ---")

        query_4 = """
            SELECT
                ROUND(AVG(actual_total_load_mw), 2),
                ROUND(AVG(day_ahead_total_load_forecast_mw), 2),
                ROUND(AVG(
                    day_ahead_total_load_forecast_mw
                    - actual_total_load_mw
                ), 2),
                ROUND(
                    100.0 * AVG(
                        ABS(
                            actual_total_load_mw
                            - day_ahead_total_load_forecast_mw
                        ) / NULLIF(actual_total_load_mw, 0)
                    ), 2
                )
            FROM electricity_demand
            WHERE actual_total_load_mw IS NOT NULL
              AND day_ahead_total_load_forecast_mw IS NOT NULL;
        """

        actual, forecast, bias, mape = (
            connection.execute(query_4).fetchone()
        )

        print(f"Average actual demand: {actual} MW")
        print(f"Average forecast demand: {forecast} MW")
        print(f"Forecast bias: {bias} MW")
        print(f"MAPE: {mape}%")

        # QUERY 5: Identify the largest forecast errors
        print("\n--- TOP 10 FORECAST ERRORS ---")

        query_5 = """
            SELECT
                interval_start_utc,
                ROUND(actual_total_load_mw, 2),
                ROUND(day_ahead_total_load_forecast_mw, 2),
                ROUND(
                    actual_total_load_mw
                    - day_ahead_total_load_forecast_mw, 2
                ) AS forecast_error_mw
            FROM electricity_demand
            WHERE actual_total_load_mw IS NOT NULL
              AND day_ahead_total_load_forecast_mw IS NOT NULL
            ORDER BY ABS(
                actual_total_load_mw
                - day_ahead_total_load_forecast_mw
            ) DESC
            LIMIT 10;
        """

        for timestamp, actual, forecast, error in connection.execute(query_5):
            print(
                f"{timestamp} | "
                f"Actual: {actual} MW | "
                f"Forecast: {forecast} MW | "
                f"Error: {error} MW"
            )


if __name__ == "__main__":
    analyze_demand()
