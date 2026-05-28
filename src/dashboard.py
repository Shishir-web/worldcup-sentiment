"""
src/dashboard.py
----------------
Plotly Dash app.  Run with:
    python app.py
 
Refreshes every 5 seconds via dcc.Interval.  The sentiment analyser is
called on each tick to drain the tweet queue and compute the latest batch.
"""

import time
import collections
import logging

import pandas as pd 
import plotly.graph_objects as go
from dash import Dash, dcc, html, Output, Input, callback

logger = logging.getLogger(__name__)

#Colour palette
C_POS = "#22C55E"  # green
C_NEU = "#EAB308"  # yellow
C_NEG = "#EF4444"  # red
C_GOAL = "#f97316"  # orange marker for goal events
C_BG = "#0F172A"   # dark background
C_TEXT = "#E2E8F0" # light text
C_GRID = "#334155" # grid lines
C_CARD = "#1E293B" # card background

REFRESH_INTERVAL_MS = 5000  # how often the dashboard updates (and calls the analyser to drain the queue)

def _sentiment_color(score: float) -> str:
    """Helper to map sentiment score to a color."""
    if score > 0.15:
        return C_POS
    elif score < -0.15:
        return C_NEG
    return C_NEU


def build_app(analyser) -> Dash:
    """
    Create and return the Dash app, wired to *analyser*.
    """
    app = Dash(__name__, title="⚽ World Cup Sentiment Tracker")

    #-- Layout ------------------------------------------------
    app.layout = html.Div(
        style={"backgroundColor": C_BG, "minHeight": "100vh", "padding": "24px", "color": C_TEXT, "font-family": "Arial, sans-serif"},
        children=[
            #Header
            html.Div(
                style={"marginBottom": "24px"},
                children=[
                    html.H1("⚽ World Cup Sentiment Tracker",
                            style={"color": C_TEXT, "margin": 0, "fontSize": "28px", "fontWeight": 600}),
                    html.P("Real-time public sentiment from Twitter/X during the match",
                           style={"color": C_NEU, "marginTop": "6px", "fontSize": "14px"}),
                ],
            ),

            # KPI row
            html.Div(
                id="kpi-row",
                style={"display": "flex", "gap": "16px", "marginBottom": "24px"},
            ),

            # Main chart
            html.Div(
                style={"backgroundColor": C_CARD, "borderRadius": "12px", "padding": "20px", "marginBottom": "20px"},
                children=[
                    html.H3("Sentiment over time", style={"color": C_TEXT, "marginTop": 0, "fontSize": "16px", "fontWeight": 500}),
                    dcc.Graph(id="sentiment-chart", config={"displayModeBar": False}),
                ],
            ),

            # Distribution + tweet volume side by side
            html.Div(
                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginBottom": "20px"},
                children=[
                    html.Div(
                        style={"backgroundColor": C_CARD, "borderRadius": "12px", "padding": "20px"},
                        children=[
                            html.H3("Sentiment distribution", style={"color": C_TEXT, "marginTop": 0, "fontSize": "16px", "fontWeight": 500}),
                            dcc.Graph(id="dist-chart", config={"displayModeBar": False}),
                        ],
                    ),
                    html.Div(
                        style={"backgroundColor": C_CARD, "borderRadius": "12px", "padding": "20px"},
                        children=[
                            html.H3("Tweets per batch", style={"color": C_TEXT, "marginTop": 0, "fontSize": "16px", "fontWeight": 500}),
                            dcc.Graph(id="volume-chart", config={"displayModeBar": False}),
                        ],
                    ),
                ],
            ),

            # Interval
            dcc.Interval(id="ticker", interval=REFRESH_INTERVAL_MS, n_intervals=0),
        ],
    )

    #-- Callbacks ------------------------------------------------

    @callback(
        Output("kpi-row", "children"),
        Output("sentiment-chart", "figure"),
        Output("dist-chart", "figure"),
        Output("volume-chart", "figure"),
        Input("ticker", "n_intervals"),
    )
    def update(_n):
        #Drain queue and classify new tweets
        analyser.process_batch()

        history = analyser.get_history()
        goal_timestamps = analyser.get_goal_events()

        if not history:
            empty = go.FIgure()
            empty.upgrade_layout(**_base_layout())
            return [], empty, empty, empty

        df = pd.DataFrame(
            {
                "time": [p.timestamp for p in history],
                "score": [p.score for p in history],
                "count": [p.tweet_count for p in history],
                "goal": [p.is_goal_event for p in history],
            }
        )
        df["dt"] = pd.to_datetime(df["time"], unit="s")

        latest = df["score"].iloc[-1]
        avg = df["score"].mean()
        total = df["count"].sum()
        goals = len(goal_timestamps)

        #-- KPIs ------------------------------------------------
        kpis = _kpi_row(latest, avg, int(total), goals)

        #-- Sentiment timeline ----------------------------------------
        timeline = go.Figure()

        #Shaded fill under the line, colored by sentiment
        timeline.add_trace(go.Scatter(
            x=df["dt"], y=df["score"],
            mode="lines",
            fill="tozeroy",
            line=dict(color=C_POS if avg >= 0 else C_NEG, width=2),
            fillcolor=f"rgba({'34,197,94' if avg >= 0 else '239,68,68'},0.12)",
            name="Sentiment",
            hovertemplate="%{x|%H:%M:%S}<br>Score: %{y:.2f}<extra></extra>",
        ))

        #Zero reference line
        timeline.add_hline(y=0, line_dash="dot", line_color=C_GRID, line_width=1)

        #Goal annotations
        for ts in goal_timestamps:
            dt_goal = pd.to_datetime(ts, unit="s")
            timeline.add_vline(
                x=dt_goal.timestamp() * 1000,  # convert to ms for plotly
                line_color=C_GOAL, line_dash="dash", line_width=2,
                annotation_text="⚽ Goal!", annotation_position="top right",
                annotation_font_size=12, annotation_font_color=C_GOAL,
            )

        timeline.update_layout(
            **_base_layout(),
            yaxis=dict(range=[-1.1, 1.1], tickvals=[-1, -0.5, 0, 0.5, 1]), color=C_NEU,
            xaxis=dict(color=C_NEU),
            height=300,
            margin=dict(l=0, r=0, t=10, b=0),
            showlegend=False,
        )

        #--Distribution donut -----------------------------------------
        n_pos = (df["score"] > 0.15).sum()
        n_neu = ((df["score"] >= -0.15) & (df["score"] <= 0.15)).sum()
        n_neg = (df["score"] < -0.15).sum()
        dist = go.Figure(go.Pie(
            labels=["Positive", "Neutral", "Negative"],
            values=[n_pos, n_neu, n_neg],
            hole=0.55,
            textinfo="percent",
            hoverinfo="label+value",
        ))
        dist.update_traces(**_base_layout(), height=220, margin=dict(l=0, r=0, t=10, b=0))

        #--Volume bar chart -----------------------------------------
        volume = go.Figure(go.Bar(
            x=df["dt"], y=df["count"],
            marker_color=[C_GOAL if g else C_TEXT for g in df["goal"]],
            hovertemplate="%{x|%H:%M:%S}<br>Count: %{y}<extra></extra>",
        ))
        volume.update_layout(
            **_base_layout(),
            yaxis=dict(color=C_NEU),
            xaxis=dict(color=C_NEU),
            height=220,
            margin=dict(l=0, r=0, t=10, b=0),
            showlegend=False,
        )

        return kpis, timeline, dist, volume

        return app

#-- Helper functions for building the dashboard components ------------------------------
def _base_layout() -> dict:
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=C_TEXT, family="Arial, sans-serif"),
        xaxis=dict(gridcolor=C_GRID, zerolinecolor=C_GRID),
        yaxis=dict(gridcolor=C_GRID, zerolinecolor=C_GRID),
)     

def _kpi_card(label: str, value: str, color: str) -> html.Div:
    return html.Div(
        style={
            "backgroundColor": C_CARD, 
            "borderRadius": "12px", 
            "padding": "16px 20px", 
            "flex": "1",
            "borderLeft": f"4px solid {color}",
        },
        children=[
            html.P(label, style={"color": C_NEU, "fontSize": "12px", "margin": 0, "textTransform": "uppercase", "letterSpacing": "0.05em"}),
            html.P(value, style={"color": C_TEXT, "fontSize": "28px", "margin": "4px 0 0", "fontSize": "24px", "fontWeight": 600}),
        ],
    )

def _kpi_row(latest: float, avg: float, total: int, goals: int) -> list:
    lat_color = _sentiment_color(latest)
    avg_color = _sentiment_color(avg)
    return [
        _kpi_card("Latest sentiment", f"{latest:+.2f}", lat_color),
        _kpi_card("Average sentiment", f"{avg:+.2f}", avg_color),
        _kpi_card("Total tweets", f"{total}", C_NEU),
        _kpi_card("Goal events", f"{goals}", C_GOAL),
    ]


            


 