"""

Script for SQL integration in the workflow: loading the cleaned pipeline data into a real SQL
database, then computing two of the existing KPIs using SQL (GROUP BY, subqueries, and LAG() 
built-in window function) instead of pandas, to demonstrate
the same logic in both paradigms.

NOTE: sqlite3 is part of Python's standard library, and the database is just a single .db file on disk.
"""

import sqlite3
import pandas as pd
from pathlib import Path

TABLE_NAME = "emissions"


def load_to_db(csv_path, db_path, table_name=TABLE_NAME):
    """Read a cleaned CSV into a SQLite table (replacing it if it exists)."""
    csv_path = Path(csv_path)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)
    conn = sqlite3.connect(db_path)
    try:
        df.to_sql(table_name, conn, if_exists="replace", index=False)
    finally:
        conn.close()
    return len(df)


def total_co2_latest_year_sql(db_path, table_name=TABLE_NAME):
    """
    Same result as kpi.total_co2_by_entity(), computed in SQL.
    The subquery finds the latest year; the outer query ranks entities
    within that year.
    """
    query = f"""
        SELECT country, co2
        FROM {table_name}
        WHERE year = (SELECT MAX(year) FROM {table_name})
        ORDER BY co2 DESC
    """
    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query(query, conn)
    finally:
        conn.close()


def yoy_change_sql(db_path, table_name=TABLE_NAME):
    """
    Same result as kpi.yoy_change_pct(), computed in SQL using a window
    function (LAG) instead of pandas' groupby().pct_change().
    """
    query = f"""
        SELECT
            country,
            year,
            co2,
            (co2 - LAG(co2) OVER (PARTITION BY country ORDER BY year))
                / LAG(co2) OVER (PARTITION BY country ORDER BY year) * 100
                AS yoy_change_pct
        FROM {table_name}
        ORDER BY country, year
    """
    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query(query, conn)
    finally:
        conn.close()


def run(processed_path, db_path, output_dir):
    processed_path = Path(processed_path)
    db_path = Path(db_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    n_rows = load_to_db(processed_path, db_path)

    total_co2_latest_year_sql(db_path).to_csv(output_dir / "kpi_total_co2_latest_sql.csv", index=False)
    yoy_change_sql(db_path).to_csv(output_dir / "kpi_yoy_change_sql.csv", index=False)

    print(f"Loaded {n_rows} rows into {db_path}, ran 2 SQL-based KPIs into {output_dir}")


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    run(
        processed_path=base / "data/processed/portfolio_clean.csv",
        db_path=base / "data/pipeline.db",
        output_dir=base / "data/processed/kpis",
    )
