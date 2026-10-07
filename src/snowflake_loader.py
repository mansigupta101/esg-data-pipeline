"""
Step 5 in the pipeline: load the four star-schema CSVs (written by
star_schema.py) into Snowflake as FACT_EMISSIONS, FACT_DATA_QUALITY,
DIM_ENTITY, DIM_DATE.

Connection comes entirely from .env (python-dotenv, override=True), using
key-pair auth (SNOWFLAKE_JWT) instead of a password/PAT -- no secret
value to copy-paste or mistype:

    SNOWFLAKE_ACCOUNT
    SNOWFLAKE_USER
    SNOWFLAKE_PRIVATE_KEY_PATH   (path to the .p8 private key file)
    SNOWFLAKE_ROLE
    SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_DATABASE           (defaults to ESG_DEV if unset)

Each table is fully replaced on every run (overwrite=True) -- this
pipeline is small and re-runnable from source, so there's no
incremental-load logic here. Revisit if the data volume or update
pattern changes.
"""

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

load_dotenv(override=True)

TABLES = {
    "DIM_ENTITY": "DimEntity.csv",
    "DIM_DATE": "DimDate.csv",
    "FACT_EMISSIONS": "FactEmissions.csv",
    "FACT_DATA_QUALITY": "FactDataQuality.csv",
}


def get_connection():
    """
    Open a Snowflake connection using key-pair auth. The connector reads
    and parses the private key file itself -- no manual PEM/DER handling
    needed here, just the file path and (if the key is encrypted) its
    passphrase.
    """
    database = os.environ.get("SNOWFLAKE_DATABASE", "ESG_DEV")
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        authenticator="SNOWFLAKE_JWT",
        private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
        private_key_file_pwd=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PWD"),  # None if unset = unencrypted key
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=database,
        schema="PUBLIC",
    )


def load_table(conn, table_name, csv_path):
    """
    Load one CSV into one Snowflake table, replacing its contents.
    auto_create_table=True builds the table from the dataframe's dtypes
    the first time it's run; overwrite=True truncates and reloads on
    every run after that.
    """
    df = pd.read_csv(csv_path)
    success, n_chunks, n_rows, _ = write_pandas(
        conn,
        df,
        table_name,
        auto_create_table=True,
        overwrite=True,
    )
    if not success:
        raise RuntimeError(f"write_pandas reported failure loading {table_name}")
    return n_rows


def run(star_schema_dir):
    star_schema_dir = Path(star_schema_dir)
    conn = get_connection()
    try:
        results = {}
        for table_name, filename in TABLES.items():
            csv_path = star_schema_dir / filename
            if not csv_path.exists():
                raise FileNotFoundError(
                    f"{csv_path} not found -- run star_schema.py first."
                )
            results[table_name] = load_table(conn, table_name, csv_path)
        return results
    finally:
        conn.close()


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    results = run(star_schema_dir=base / "outputs")
    for table_name, n_rows in results.items():
        print(f"{table_name}: {n_rows} rows loaded into "
              f"{os.environ.get('SNOWFLAKE_DATABASE', 'ESG_DEV')}.PUBLIC")
