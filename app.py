import threading
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html, dash_table, Input, Output
import plotly.graph_objects as go

from scraper import load_data

UPDATE_MINUTES = 5    # how often the server re-scrapes BBC
UI_POLL_SECONDS = 30  # how often the browser checks for new data

# ---------- theme ----------
BLACK, DARK, WHITE, YELLOW = "#000000", "#111111", "#FFFFFF", "#FFD700"
YELLOW_SCALE = ["#6b5a00", YELLOW]

TAB_STYLE = {"backgroundColor": BLACK, "color": YELLOW, "border": "1px solid #333",
             "padding": "12px", "fontWeight": "bold"}
TAB_SELECTED = {**TAB_STYLE, "backgroundColor": "#1a1a1a", "borderTop": f"3px solid {YELLOW}"}

# ---------- live data ----------
state = {}
lock = threading.Lock()
refresh_lock = threading.Lock()
last_check = 0


def update_data():
    """Scrape and store the result; never replace live data with sample data."""
    global last_check
    with refresh_lock:
        if state and time.monotonic() - last_check < UPDATE_MINUTES * 60:
            return
        table, scorers, assists, source = load_data()
        with lock:
            state.update(table=table, scorers=scorers, assists=assists,
                         source=source, updated=datetime.now())
            last_check = time.monotonic()


# ---------- app ----------
app = Dash(__name__, title="Premier League Dashboard")
server = app.server

# Page background + dropdown colours (Dash can't style <body> from the layout)
app.index_string = '''<!DOCTYPE html>
<html>
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
{%css%}
<style>
  body { background:#000; color:#fff; margin:0; font-family:sans-serif; }
  .Select-control, .Select-menu-outer, .Select-option { background:#111 !important; color:#fff !important; border-color:#444 !important; }
  .Select-value-label, .Select-placeholder, .Select-input > input { color:#fff !important; }
  .Select-option.is-focused { background:#333 !important; }
  .Select--multi .Select-value { background:#333 !important; color:#FFD700 !important; border-color:#555 !important; }
  .Select--multi .Select-value-icon { color:#FFD700 !important; border-color:#555 !important; }
</style>
</head>
<body>
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>'''


def tab(label, children):
    return dcc.Tab(label=label, children=children, style=TAB_STYLE, selected_style=TAB_SELECTED)


app.layout = html.Div(style={"maxWidth": "1100px", "margin": "auto", "padding": "16px", "color": WHITE}, children=[
    html.Div("THE MATCHDAY NOTEBOOK", className="eyebrow"),
    html.H1("Premier League Analytics", style={"color": YELLOW}),
    html.P("Explore the table. Compare clubs. Follow the goals.", className="subtitle"),
    html.Div([
        html.Button("Check for updates", id="refresh", n_clicks=0,
                    style={"backgroundColor": YELLOW, "color": BLACK, "border": "none",
                           "padding": "6px 14px", "fontWeight": "bold", "cursor": "pointer"}),
        html.Span(id="source", style={"marginLeft": "12px", "color": "#bbbbbb"}),
    ], style={"marginBottom": "12px"}),
    dcc.Store(id="store"),
    html.Div(id="summary", className="summary"),
    dcc.Interval(id="tick", interval=UI_POLL_SECONDS * 1000),
    dcc.Tabs(colors={"border": "#333", "primary": YELLOW, "background": DARK}, children=[
        tab("League Table", html.Div(id="tab-table")),
        tab("Top Scorers", [
            dcc.Slider(3, 15, 1, value=10, id="n-scorers", marks=None,
                       tooltip={"placement": "bottom", "always_visible": True}),
            dcc.Graph(id="scorers-graph"),
        ]),
        tab("Top Assists", [
            dcc.Slider(3, 15, 1, value=10, id="n-assists", marks=None,
                       tooltip={"placement": "bottom", "always_visible": True}),
            dcc.Graph(id="assists-graph"),
        ]),
        tab("Points Comparison", [
            dcc.Dropdown(id="teams", multi=True, placeholder="Select teams (default: top 6)"),
            dcc.Graph(id="points-graph"),
        ]),
        tab("Goals by Team", [
            dcc.RadioItems(["GF", "GA", "GD"], "GF", id="goal-metric", inline=True,
                           labelStyle={"marginRight": "16px", "color": WHITE}),
            dcc.Graph(id="goals-graph"),
        ]),
    ]),
    html.P("P: played · W: wins · D: draws · L: losses · GF: goals for · GA: goals against · GD: goal difference · Pts: points. Row shading marks positions 1–4 and 18–20, not confirmed qualification.", className="footnote"),
    html.Div([html.A("BBC Sport standings", href="https://www.bbc.com/sport/football/premier-league/table", target="_blank"), " · ", html.A("BBC player statistics", href="https://www.bbc.com/sport/football/premier-league/top-scorers", target="_blank"), " · ", html.A("ESPN standings", href="https://www.espn.com/soccer/standings/_/league/eng.1", target="_blank")], className="footnote"),
])


def style_fig(fig):
    """Black background, white text, yellow title."""
    fig.update_layout(template="plotly_dark", paper_bgcolor=BLACK, plot_bgcolor=BLACK,
                      font_color=WHITE, title_font_color=YELLOW)
    return fig


def players_fig(records, stat, n, title):
    if not records:
        return empty_fig("Player statistics unavailable. Try again later or run demo mode.")
    df = pd.DataFrame(records).head(n)
    fig = px.bar(df, x=stat, y="Player", orientation="h", color=stat,
                 color_continuous_scale=YELLOW_SCALE, title=title,
                 hover_data=[c for c in ["Team"] if c in df.columns])
    fig.update_layout(yaxis={"autorange": "reversed"})
    return style_fig(fig)


# ---------- callbacks ----------
def empty_fig(message):
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return style_fig(fig)


@app.callback(Output("summary", "children"), Input("store", "data"))
def summary(data):
    rows = (data or {}).get("table", [])
    if not rows:
        return html.P("Standings unavailable. Check the source status below the update button.")
    cards = [("LEAGUE LEADER", rows[0]["Team"]), ("LEADER POINTS", rows[0]["Pts"]),
             ("GOALS SCORED", sum(r["GF"] for r in rows)), ("CLUBS", len(rows))]
    return [html.Div([html.Small(label), html.Strong(str(value))], className="stat-card") for label, value in cards]

@app.callback(Output("store", "data"), Output("source", "children"),
              Input("tick", "n_intervals"), Input("refresh", "n_clicks"))
def refresh(_n, _clicks):
    update_data()
    with lock:
        data = {"table": state["table"].to_dict("records"),
                "scorers": state["scorers"].to_dict("records"),
                "assists": state["assists"].to_dict("records")}
        label = (f"Source: {state['source']} | Last checked (server time): {state['updated']:%H:%M:%S} "
                 f"| checks limited to once every {UPDATE_MINUTES} min")
    return data, label


@app.callback(Output("tab-table", "children"), Input("store", "data"))
def show_table(data):
    if not data or not data.get("table"):
        return html.P("No standings available. Live data will appear after a successful scrape.")
    return dash_table.DataTable(
        data=data["table"],
        columns=[{"name": c, "id": c} for c in data["table"][0]],
        sort_action="native", filter_action="native", page_size=20,
        export_format="csv",
        style_table={"border": "1px solid #333", "overflowX": "auto"},
        style_cell={"backgroundColor": BLACK, "color": WHITE, "border": "1px solid #222"},
        style_cell_conditional=[{"if": {"column_id": "Team"}, "textAlign": "left"}],
        style_header={"backgroundColor": DARK, "color": YELLOW, "fontWeight": "bold",
                      "border": "1px solid #333"},
        style_data_conditional=[
            {"if": {"filter_query": "{Pos} <= 4"}, "backgroundColor": "#0f3d1f"},
            {"if": {"filter_query": "{Pos} >= 18"}, "backgroundColor": "#4a1414"},
        ],
    )


@app.callback(Output("scorers-graph", "figure"), Input("store", "data"), Input("n-scorers", "value"))
def scorers_fig(data, n):
    return players_fig((data or {}).get("scorers", []), "Goals", n, "Top Scorers")


@app.callback(Output("assists-graph", "figure"), Input("store", "data"), Input("n-assists", "value"))
def assists_fig(data, n):
    return players_fig((data or {}).get("assists", []), "Assists", n, "Top Assists")


@app.callback(Output("teams", "options"), Input("store", "data"))
def team_options(data):
    return [r["Team"] for r in (data or {}).get("table", [])]


@app.callback(Output("points-graph", "figure"), Input("store", "data"), Input("teams", "value"))
def points_fig(data, teams):
    if not data or not data.get("table"):
        return empty_fig("Standings unavailable")
    df = pd.DataFrame(data["table"])
    df = df[df["Team"].isin(teams)] if teams else df.head(6)
    return style_fig(px.bar(df, x="Team", y="Pts", color="Team", text="Pts", title="Points Comparison"))


@app.callback(Output("goals-graph", "figure"), Input("store", "data"), Input("goal-metric", "value"))
def goals_fig(data, metric):
    if not data or not data.get("table"):
        return empty_fig("Standings unavailable")
    df = pd.DataFrame(data["table"]).sort_values(metric, ascending=False)
    names = {"GF": "Goals Scored", "GA": "Goals Conceded", "GD": "Goal Difference"}
    return style_fig(px.bar(df, x="Team", y=metric, color=metric,
                            color_continuous_scale=YELLOW_SCALE, title=names[metric]))


if __name__ == "__main__":
    app.run(debug=False)
