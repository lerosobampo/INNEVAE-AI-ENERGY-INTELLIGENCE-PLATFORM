
"""
INNEVA.E - WHOLESALE PRICE IMPUTATION
Checkpoint 14.3B

Method:
- Calculate the September 2026 mean wholesale price.
- Fill missing analytical values with that mean.
- Preserve the original wholesale_prices table.
- Flag imputed observations.
- Recreate dependent analytical views safely.

Run:
    python3 src/database/impute_wholesale_prices.py
"""

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = (
    PROJECT_ROOT
    / "data"
    / "database"
    / "innevae_platform.db"
)


def main():

    print("=" * 65)
    print("INNEVA.E - WHOLESALE PRICE IMPUTATION")
    print("=" * 65)

    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_PATH}"
        )

    with sqlite3.connect(DATABASE_PATH) as connection:

        connection.row_factory = sqlite3.Row

        # Inspect the original source table.
        source = connection.execute(
            """
            SELECT
                COUNT(*) AS observed_rows,
                AVG(wholesale_price_eur_mwh) AS historical_mean
            FROM wholesale_prices
            WHERE interval_start_utc >= '2026-09-01'
              AND interval_start_utc < '2026-10-01'
            """
        ).fetchone()

        historical_mean = source["historical_mean"]

        if historical_mean is None:
            raise ValueError(
                "No historical wholesale prices available."
            )

        print("\nSOURCE DATA")
        print("-" * 65)
        print(f"Observed price rows: {source['observed_rows']}")
        print(f"Historical mean: {historical_mean:.6f} EUR/MWh")

        # Verify that the integrated view contains the
        # expected two missing prices.
        missing = connection.execute(
            """
            SELECT interval_start_utc
            FROM integrated_energy_intelligence
            WHERE wholesale_price_eur_mwh IS NULL
            ORDER BY interval_start_utc
            """
        ).fetchall()

        missing_timestamps = [
            row["interval_start_utc"]
            for row in missing
        ]

        print("\nMISSING PRICE TIMESTAMPS")
        print("-" * 65)

        for timestamp in missing_timestamps:
            print(timestamp)

        if len(missing_timestamps) != 2:
            raise ValueError(
                "Expected exactly 2 missing wholesale prices; "
                f"found {len(missing_timestamps)}. "
                "No changes made."
            )

        # We add a new view rather than overwrite the source.
        #
        # SQLite view dependencies are resolved when queried,
        # so the integrated model can remain unchanged for now.
        #
        # The new view includes the original integrated
        # columns plus imputation metadata.

        connection.execute(
            """
            DROP VIEW IF EXISTS
                integrated_energy_intelligence_imputed
            """
        )

        connection.execute(
            """
            CREATE VIEW integrated_energy_intelligence_imputed AS

            WITH historical_average AS (
                SELECT
                    AVG(wholesale_price_eur_mwh)
                        AS mean_price
                FROM wholesale_prices
                WHERE interval_start_utc >= '2026-09-01'
                  AND interval_start_utc < '2026-10-01'
            )

            SELECT
                e.*,

                COALESCE(
                    e.wholesale_price_eur_mwh,
                    h.mean_price
                ) AS wholesale_price_imputed_eur_mwh,

                CASE
                    WHEN e.wholesale_price_eur_mwh IS NULL
                    THEN 1
                    ELSE 0
                END AS wholesale_price_was_imputed,

                CASE
                    WHEN e.wholesale_price_eur_mwh IS NULL
                    THEN 'historical_mean'
                    ELSE 'observed'
                END AS wholesale_price_source

            FROM integrated_energy_intelligence AS e
            CROSS JOIN historical_average AS h
            """
        )

        # Validate the imputed analytical view.
        validation = connection.execute(
            """
            SELECT
                COUNT(*) AS total_rows,

                COUNT(wholesale_price_imputed_eur_mwh)
                    AS available_prices,

                SUM(wholesale_price_was_imputed)
                    AS imputed_prices,

                AVG(wholesale_price_imputed_eur_mwh)
                    AS mean_after_imputation

            FROM integrated_energy_intelligence_imputed
            """
        ).fetchone()

        if validation["total_rows"] != 720:
            raise ValueError(
                "Unexpected row count after imputation."
            )

        if validation["available_prices"] != 720:
            raise ValueError(
                "Missing prices remain after imputation."
            )

        if validation["imputed_prices"] != 2:
            raise ValueError(
                "Unexpected number of imputed prices."
            )

        print("\nVALIDATION RESULTS")
        print("-" * 65)

        print(
            f"Total hourly records: "
            f"{validation['total_rows']}"
        )

        print(
            f"Available analytical prices: "
            f"{validation['available_prices']}"
        )

        print(
            f"Imputed observations: "
            f"{validation['imputed_prices']}"
        )

        print(
            f"Average after imputation: "
            f"{validation['mean_after_imputation']:.6f} EUR/MWh"
        )

        print("\nImputed records:")
        print("-" * 65)

        rows = connection.execute(
            """
            SELECT
                interval_start_utc,
                wholesale_price_eur_mwh,
                wholesale_price_imputed_eur_mwh,
                wholesale_price_source
            FROM integrated_energy_intelligence_imputed
            WHERE wholesale_price_was_imputed = 1
            ORDER BY interval_start_utc
            """
        ).fetchall()

        for row in rows:
            print(
                f"{row['interval_start_utc']} | "
                f"{row['wholesale_price_imputed_eur_mwh']:.6f} | "
                f"{row['wholesale_price_source']}"
            )

    print("\nImputation completed successfully.")


if __name__ == "__main__":
    main()
