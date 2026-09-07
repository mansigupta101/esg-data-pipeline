"""
Script to create plotly-Dash dashboard, reading the KPI outputs produced by src/kpi.py.
Run with: python dashboard/app.py, then open http://127.0.0.1:8050

To install plotly dash use: 'pip install dash plotly'

Panels (2x2 grid):
  1. Total CO2 by entity, selectable year (portfolio exposure ranking)
  2. YoY % change over time, by entity, with an all-countries or single-country view
  3. Portfolio-wide total GHG over time (aggregate exposure trend)
  4. Data validity by entity, colored by a validity threshold
"""

from pathlib import Path
import pandas as pd
from dash import Dash, dcc, html, Input, Output
import plotly.express as px

BASE = Path(__file__).resolve().parent.parent
KPI_DIR = BASE / "data/processed/kpis"
PROCESSED_DIR = BASE / "data/processed"

FONT_FAMILY = "'Times New Roman', Times, serif"
CO2 = "CO\u2082"  # subscript 2, for all *displayed* text -- column names stay "co2"

clean = pd.read_csv(PROCESSED_DIR / "portfolio_clean.csv")
yoy = pd.read_csv(KPI_DIR / "kpi_yoy_change.csv")
portfolio_ghg = pd.read_csv(KPI_DIR / "kpi_portfolio_ghg_total.csv")
validity = pd.read_csv(KPI_DIR / "kpi_validity_by_entity.csv")

YEARS = sorted(clean["year"].unique())
COUNTRIES = sorted(yoy["country"].unique())
VALIDITY_THRESHOLD = 0.95
# Must match YOY_JUMP_THRESHOLD in src/qc_checks.py -- kept as a separate
# constant here since the dashboard doesn't import qc_checks directly.
YOY_JUMP_THRESHOLD_PCT = 10

# ---- styling constants -----------------------------------------------------

CARD_STYLE = {
    "border": "1px solid #d8dee4",
    "borderRadius": "8px",
    "padding": "16px 24px 8px 24px",
    "boxShadow": "0 1px 3px rgba(0,0,0,0.06)",
}

GRID_STYLE = {
    "display": "grid",
    "gridTemplateColumns": "1fr 1fr",
    "gap": "24px",
}

CONTROL_ROW_STYLE = {
    "display": "flex",
    "flexDirection": "row",
    "alignItems": "center",
    "justifyContent": "flex-end",
    "gap": "10px",
    "marginBottom": "4px",
}

DROPDOWN_STYLE = {"width": "200px", "fontFamily": FONT_FAMILY}
GRAPH_STYLE = {"height": "420px"}


def apply_layout(fig):
    """Apply the page font and a tighter top margin so the figure's own
    title sits close to the control row above it, instead of floating
    with a large gap (Plotly's default top margin is quite large)."""
    fig.update_layout(
        font_family=FONT_FAMILY,
        title_font_family=FONT_FAMILY,
        margin=dict(t=50, b=50, l=60, r=30),
    )
    return fig


def make_card(control_row, graph_id_or_figure, is_id=True):
    """Build one bordered card containing a control row and its graph,
    so the dropdown and the chart it affects are visually one unit."""
    graph = dcc.Graph(id=graph_id_or_figure, style=GRAPH_STYLE) if is_id \
        else dcc.Graph(figure=graph_id_or_figure, style=GRAPH_STYLE)
    return html.Div([control_row, graph], style=CARD_STYLE)


# ---- static figures (no dropdown) ------------------------------------------

fig_portfolio = apply_layout(px.line(
    portfolio_ghg, x="year", y="portfolio_total_ghg",
    title=f"Portfolio Total GHG ({CO2}) Over Time",
    labels={"portfolio_total_ghg": f"Total GHG (Mt {CO2}eq)"},
))

OK_LABEL = "OK"
BELOW_LABEL = "Below threshold"

validity_sorted = validity.sort_values("validity_score").copy()
validity_sorted["status"] = validity_sorted["validity_score"].apply(
    lambda s: BELOW_LABEL if s < VALIDITY_THRESHOLD else OK_LABEL
)
fig_validity = apply_layout(px.bar(
    validity_sorted,
    x="country", y="validity_score", color="status",
    title="Data Validity Score by Entity",
    labels={"validity_score": "Validity (0-1)", "status": "Status"},
    range_y=[0, 1],
    color_discrete_map={BELOW_LABEL: "#d62728", OK_LABEL: "#2ca02c"},
))
# threshold note placed just under the legend (top-right), not in the title
fig_validity.add_annotation(
    xref="paper", yref="paper", x=1.02, y=0.75,
    xanchor="left", yanchor="top",
    text=f"Threshold: {VALIDITY_THRESHOLD:.0%}",
    showarrow=False, font=dict(size=12),
)

# ---- app --------------------------------------------------------------

app = Dash(__name__)
app.title = "ESG Portfolio Emissions Dashboard"

year_control = html.Div([
    html.Label("Year"),
    dcc.Dropdown(
        id="year-dropdown",
        options=[{"label": str(y), "value": y} for y in YEARS],
        value=YEARS[-1],
        clearable=False,
        style=DROPDOWN_STYLE,
    ),
], style=CONTROL_ROW_STYLE)

country_control = html.Div([
    html.Label("Country"),
    dcc.Dropdown(
        id="country-dropdown",
        options=[{"label": "All", "value": "All"}] + [{"label": c, "value": c} for c in COUNTRIES],
        value="All",
        clearable=False,
        style=DROPDOWN_STYLE,
    ),
], style=CONTROL_ROW_STYLE)

app.layout = html.Div([
    html.H1("ESG Portfolio Emissions Dashboard", style={"textAlign": "center"}),
    html.P(
        "Demo pipeline: public country-level emissions data used as a "
        "stand-in for a bank's counterparty/portfolio ESG exposure.",
        style={"textAlign": "center", "fontSize": "18px"},
    ),

    html.Div([
        make_card(year_control, "total-co2-graph", is_id=True),
        make_card(country_control, "yoy-graph", is_id=True),
        make_card(html.Div(), fig_portfolio, is_id=False),
        make_card(html.Div(), fig_validity, is_id=False),
    ], style=GRID_STYLE),
], style={"fontFamily": FONT_FAMILY, "maxWidth": "1760px", "margin": "0 auto", "padding": "24px"})


@app.callback(
    Output("total-co2-graph", "figure"),
    Input("year-dropdown", "value"),
)
def update_total_co2(selected_year):
    filtered = clean[clean["year"] == selected_year].sort_values("co2", ascending=False)
    fig = px.bar(
        filtered, x="country", y="co2",
        title=f"Total {CO2} by Entity ({selected_year})",
        labels={"co2": f"{CO2} (Mt)", "country": "Entity"},
    )
    return apply_layout(fig)


@app.callback(
    Output("yoy-graph", "figure"),
    Input("country-dropdown", "value"),
)
def update_yoy(selected_country):
    if selected_country == "All":
        fig = px.line(
            yoy, x="year", y="yoy_change_pct", color="country",
            title=f"Year-over-Year {CO2} Change by Entity (\u00b1{YOY_JUMP_THRESHOLD_PCT}% flag threshold)",
            labels={"yoy_change_pct": "YoY change (%)"},
        )
    else:
        filtered = yoy[yoy["country"] == selected_country]
        fig = px.line(
            filtered, x="year", y="yoy_change_pct",
            title=f"Year-over-Year {CO2} Change \u2014 {selected_country} (\u00b1{YOY_JUMP_THRESHOLD_PCT}% flag threshold)",
            labels={"yoy_change_pct": "YoY change (%)"},
        )
    fig.update_xaxes(dtick=1, tickangle=-45)
    # dashed reference lines showing exactly where the QA/QC flag threshold sits,
    # so it's visible rather than a hidden backend number
    fig.add_hline(y=YOY_JUMP_THRESHOLD_PCT, line_dash="dash", line_color="#d62728",
                  annotation_text=f"+{YOY_JUMP_THRESHOLD_PCT}%", annotation_position="top left")
    fig.add_hline(y=-YOY_JUMP_THRESHOLD_PCT, line_dash="dash", line_color="#d62728",
                  annotation_text=f"-{YOY_JUMP_THRESHOLD_PCT}%", annotation_position="bottom left")
    return apply_layout(fig)


if __name__ == "__main__":
    app.run(debug=True)
