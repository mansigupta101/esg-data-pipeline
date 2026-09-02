"""
Script to create plotly-Dash dashboard, reading the KPI outputs produced by src/kpi.py.
Run with: python dashboard/app.py, then open http://127.0.0.1:8050

To install plotly dash use: 'pip install dash plotly'

Panels:
  1. Total CO2 by entity, latest year (portfolio exposure ranking)
  2. YoY % change over time, by entity (trend / momentum)
  3. Portfolio-wide total GHG over time (aggregate exposure trend)
  4. Data completeness by entity (data quality panel - what a risk
     data team would use to flag entities needing better disclosure)
"""

from pathlib import Path
import pandas as pd
from dash import Dash, dcc, html
import plotly.express as px

BASE = Path(__file__).resolve().parent.parent
KPI_DIR = BASE / "data/processed/kpis"

total_co2 = pd.read_csv(KPI_DIR / "kpi_total_co2_latest.csv")
yoy = pd.read_csv(KPI_DIR / "kpi_yoy_change.csv")
portfolio_ghg = pd.read_csv(KPI_DIR / "kpi_portfolio_ghg_total.csv")
completeness = pd.read_csv(KPI_DIR / "kpi_completeness_by_entity.csv")

fig_total = px.bar(
    total_co2, x="country", y="co2",
    title="Total CO2 by Entity (Latest Year)",
    labels={"co2": "CO2 (Mt)", "country": "Entity"},
)

fig_yoy = px.line(
    yoy, x="year", y="yoy_change_pct", color="country",
    title="Year-over-Year CO2 Change by Entity (%)",
    labels={"yoy_change_pct": "YoY change (%)"},
)

fig_portfolio = px.line(
    portfolio_ghg, x="year", y="portfolio_total_ghg",
    title="Portfolio Total GHG Over Time",
    labels={"portfolio_total_ghg": "Total GHG (Mt CO2eq)"},
)

fig_completeness = px.bar(
    completeness.sort_values("completeness_score"),
    x="country", y="completeness_score",
    title="Data Completeness Score by Entity",
    labels={"completeness_score": "Completeness (0-1)"},
    range_y=[0, 1],
)

app = Dash(__name__)
app.title = "ESG Portfolio Emissions Dashboard"

app.layout = html.Div([
    html.H1("ESG Portfolio Emissions Dashboard"),
    html.P(
        "Demo pipeline: public country-level emissions data used as a "
        "stand-in for a bank's counterparty/portfolio ESG exposure."
    ),
    dcc.Graph(figure=fig_total),
    dcc.Graph(figure=fig_yoy),
    dcc.Graph(figure=fig_portfolio),
    dcc.Graph(figure=fig_completeness),
])

if __name__ == "__main__":
    app.run(debug=True)
