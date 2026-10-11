"""
Step 6 in the pipeline: AI commentary layer.

For each entity's latest reporting year, pulls the already-validated KPIs
from Snowflake (DIM_ENTITY, FACT_EMISSIONS, FACT_DATA_QUALITY), builds a
strict factual JSON payload, sends it to Gemini with a prompt that forbids
inventing causes and requires flagging data-quality issues, and writes the
resulting short commentary back to Snowflake as AI_SUMMARY.

Power BI only ever displays AI_SUMMARY.summary_text -- no AI logic runs
inside the report itself.

Requires in .env (in addition to the existing SNOWFLAKE_* vars):
    GEMINI_API_KEY   -- free tier key from https://aistudio.google.com/apikey

Requires in requirements.txt:
    requests          (instead of google-genai -- see note below)

Uses plain REST calls to the stable, long-documented generateContent
endpoint instead of the google-genai SDK's newer "Interactions API"
(client.interactions.create). That SDK path was timing out 100% of the
time with no response at all -- not a rate limit, not an auth error, a
genuine client-side 30s timeout on every single call -- which points to
that specific newer API surface being unreachable from this network while
the standard REST domain works fine. Switching to plain HTTP against
generativelanguage.googleapis.com removes the SDK as a variable entirely.
"""

import os
import json
import time
from datetime import datetime, timezone

import pandas as pd
import requests
from dotenv import load_dotenv
from snowflake.connector.pandas_tools import write_pandas

from snowflake_loader import get_connection  # reuse existing key-pair auth

load_dotenv(override=True)

MODEL = "gemini-3.1-flash-lite" 
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

PROMPT_TEMPLATE = """You are writing a short factual commentary for a corporate ESG emissions dashboard.

{entity_name} is a COUNTRY, not a company -- never use corporate language ("the company's
emissions efficiency", etc.). Use "the country's" or "{entity_name}'s" instead.

Use ONLY the values given below. Do not use any outside knowledge about this country, its
policies, or world events. Do not invent causes for any change -- if the reason for a change
isn't in the data provided, say the change happened without speculating why.

Do not claim or imply progress toward a target, goal, or commitment -- no target data is
provided. Do not call the data "reliable" or say it has "integrity" -- completeness_pct alone
does not establish reliability, only describes how many fields were populated. Stick to
describing what the numbers show, not judging how good or trustworthy they are.

Always state units explicitly: million tonnes for CO2 and GHG figures, percent for
completeness and year-over-year change. Never give a bare number with no unit.

Clearly separate OBSERVATION (what the numbers literally show) from INTERPRETATION (what it
might mean for an ESG reader) -- label interpretation as such, and keep it minimal.

If completeness_pct is below 100%, or failed_qa_checks is greater than 0, or yoy_change_pct is
null, mention that data-quality caveat ONCE, in one brief clause -- don't repeat or dwell on it.
If emissions_intensity is null, state once that it isn't available for this year and move on;
don't speculate why or return to it.

Keep the whole response under 100 words. No markdown formatting, no headers, plain sentences.

Data for {entity_name} ({year}):
{data_json}
"""


def fetch_latest_kpis(conn):
    # Column names are quoted/lowercase because write_pandas(auto_create_table=True)
    # created the tables that way from the CSVs' original lowercase headers --
    # unquoted references here would fold to uppercase and not match.
    query = """
        SELECT
            e."entity_id" AS ENTITY_ID,
            e."entity_name" AS ENTITY_NAME,
            e."region" AS REGION,
            e."category" AS CATEGORY,
            e."latest_reporting_year" AS YEAR,
            f."co2" AS TOTAL_CO2,
            f."total_ghg" AS TOTAL_GHG,
            f."emissions_intensity_co2_per_gdp_million" AS EMISSIONS_INTENSITY,
            q."completeness_pct" AS COMPLETENESS_PCT,
            q."validity" AS VALIDITY,
            q."failed_checks" AS FAILED_CHECKS
        FROM DIM_ENTITY e
        JOIN FACT_EMISSIONS f
            ON f."entity_id" = e."entity_id" AND f."year" = e."latest_reporting_year"
        LEFT JOIN FACT_DATA_QUALITY q
            ON q."entity_id" = e."entity_id" AND q."year" = e."latest_reporting_year"
    """
    return pd.read_sql(query, conn)


def fetch_prior_year_co2(conn, entity_id, year):
    """
    Looks up CO2 for year-1 directly (not via a measure) so yoy_change_pct
    here matches the same "only compare if the adjacent year's row actually
    exists" rule as the corrected Power BI YoY measure -- returns None
    (not a fabricated/compounded change) if that row is missing.
    """
    query = """
        SELECT "co2" AS CO2 FROM FACT_EMISSIONS
        WHERE "entity_id" = %(entity_id)s AND "year" = %(year)s
    """
    df = pd.read_sql(query, conn, params={"entity_id": entity_id, "year": year - 1})
    return None if df.empty else float(df["CO2"].iloc[0])


def build_payload(row, prior_co2):
    yoy = None
    if prior_co2 not in (None, 0) and pd.notna(row["TOTAL_CO2"]):
        yoy = round((row["TOTAL_CO2"] - prior_co2) / prior_co2 * 100, 2)
    # Values are pre-formatted (percent, not raw 0-1 decimal; units in the key
    # name) so the model doesn't have to guess formatting -- that's what was
    # producing "0.9091" in some summaries and "90.91%" in others.
    return {
        "total_co2_million_tonnes": round(row["TOTAL_CO2"], 2) if pd.notna(row["TOTAL_CO2"]) else None,
        "total_ghg_million_tonnes": round(row["TOTAL_GHG"], 2) if pd.notna(row["TOTAL_GHG"]) else None,
        "emissions_intensity_kg_co2_per_usd_gdp": round(row["EMISSIONS_INTENSITY"] * 1000, 4) if pd.notna(row["EMISSIONS_INTENSITY"]) else None,
        "yoy_change_pct": yoy,
        "completeness_pct": round(row["COMPLETENESS_PCT"] * 100, 2) if pd.notna(row["COMPLETENESS_PCT"]) else None,
        "failed_qa_checks": int(row["FAILED_CHECKS"]) if pd.notna(row["FAILED_CHECKS"]) else None,
        "region": row["REGION"],
        "income_category": row["CATEGORY"],
    }


def call_gemini(api_key, entity_name, year, payload, max_attempts=3):
    """
    Plain REST call to generateContent (not the SDK's Interactions API --
    see module docstring). Retries on transient errors (occasional 5xx/429
    blips) before giving up on this one entity.
    """
    prompt = PROMPT_TEMPLATE.format(
        entity_name=entity_name, year=year, data_json=json.dumps(payload, indent=2)
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(
                GEMINI_URL,
                params={"key": api_key},
                json=body,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            last_err = e
            wait = 5 * attempt
            print(f"  attempt {attempt}/{max_attempts} failed ({e.__class__.__name__}: {e}); retrying in {wait}s")
            time.sleep(wait)
    raise last_err


def run():
    conn = get_connection()
    api_key = os.environ["GEMINI_API_KEY"]
    try:
        kpis = fetch_latest_kpis(conn)
        if kpis.empty:
            raise RuntimeError("No rows returned from DIM_ENTITY/FACT_EMISSIONS join -- check tables are loaded.")

        results = []
        failed = []
        for _, row in kpis.iterrows():
            try:
                prior_co2 = fetch_prior_year_co2(conn, row["ENTITY_ID"], int(row["YEAR"]))
                payload = build_payload(row, prior_co2)
                summary = call_gemini(api_key, row["ENTITY_NAME"], int(row["YEAR"]), payload)
                results.append({
                    "entity_id": row["ENTITY_ID"],
                    "year": int(row["YEAR"]),
                    "summary_text": summary,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                })
                print(f"{row['ENTITY_NAME']} ({int(row['YEAR'])}): done")
            except Exception as e:
                # Don't let one entity's failure (after retries) take down
                # the rest of the run -- log it, skip it, keep going.
                failed.append(row["ENTITY_NAME"])
                print(f"{row['ENTITY_NAME']} ({int(row['YEAR'])}): FAILED -- {e.__class__.__name__}: {e}")
            time.sleep(4)  # light pacing; plain requests calls fail/raise immediately, no hidden SDK retry loop to worry about

        if not results:
            raise RuntimeError("Every entity failed -- nothing to write. See errors above.")
        if failed:
            print(f"\n{len(failed)} entities failed and were skipped: {', '.join(failed)}")
            print("Re-run the script to retry them (this run's successes will still be overwritten together with a full re-run, so re-run the whole thing).")

        out_df = pd.DataFrame(results)
        success, _, n_rows, _ = write_pandas(
            conn, out_df, "AI_SUMMARY", auto_create_table=True, overwrite=True
        )
        if not success:
            raise RuntimeError("write_pandas reported failure loading AI_SUMMARY")
        print(f"\nAI_SUMMARY: {n_rows} rows loaded into {os.environ.get('SNOWFLAKE_DATABASE', 'ESG_DEV')}.PUBLIC")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
