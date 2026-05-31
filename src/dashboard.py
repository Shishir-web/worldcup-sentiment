import logging
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, html, dcc, Input, Output, callback

logger = logging.getLogger(__name__)

C_POS  = "#22c55e"
C_NEU  = "#94a3b8"
C_NEG  = "#ef4444"
C_GOAL = "#f97316"
C_BG   = "#0f172a"
C_CARD = "#1e293b"
C_TEXT = "#e2e8f0"
C_GRID = "#334155"
REFRESH_MS = 5000

def _sentiment_color(score):
    if score > 0.15:  return C_POS
    if score < -0.15: return C_NEG
    return C_NEU

def build_app(analyser):
    app = Dash(__name__, title="⚽ World Cup Sentiment Tracker")
    app.layout = html.Div(
        style={"backgroundColor": C_BG, "minHeight": "100vh", "padding": "24px", "fontFamily": "system-ui"},
        children=[
            html.H1("⚽ World Cup Sentiment Tracker", style={"color": C_TEXT, "margin": 0, "fontSize": "28px"}),
            html.P("Real-time sentiment from Reddit during the match", style={"color": C_NEU, "marginTop": "6px"}),
            html.Div(id="kpi-row", style={"display": "flex", "gap": "16px", "margin": "24px 0"}),
            html.Div(style={"backgroundColor": C_CARD, "borderRadius": "12px", "padding": "20px", "marginBottom": "20px"}, children=[
                html.H3("Sentiment over time", style={"color": C_TEXT, "marginTop": 0}),
                dcc.Graph(id="sentiment-chart", config={"displayModeBar": False}),
            ]),
            html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}, children=[
                html.Div(style={"backgroundColor": C_CARD, "borderRadius": "12px", "padding": "20px"}, children=[
                    html.H3("Sentiment distribution", style={"color": C_TEXT, "marginTop": 0}),
                    dcc.Graph(id="dist-chart", config={"displayModeBar": False}),
                ]),
                html.Div(style={"backgroundColor": C_CARD, "borderRadius": "12px", "padding": "20px"}, children=[
                    html.H3("Comments per batch", style={"color": C_TEXT, "marginTop": 0}),
                    dcc.Graph(id="volume-chart", config={"displayModeBar": False}),
                ]),
            ]),
            dcc.Interval(id="ticker", interval=REFRESH_MS, n_intervals=0),
        ],
    )

    @callback(
        Output("kpi-row", "children"),
        Output("sentiment-chart", "figure"),
        Output("dist-chart", "figure"),
        Output("volume-chart", "figure"),
        Input("ticker", "n_intervals"),
    )
    def update(_n):
        analyser.process_batch()
        history = analyser.get_history()
        goal_timestamps = analyser.get_goal_events()

        def empty_fig():
            fig = go.Figure()
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font=dict(color=C_TEXT), xaxis=dict(gridcolor=C_GRID),
                              yaxis=dict(gridcolor=C_GRID))
            return fig

        if not history:
            return [], empty_fig(), empty_fig(), empty_fig()

        import pandas as pd
        df = pd.DataFrame({
            "time":  [p.timestamp for p in history],
            "score": [p.score for p in history],
            "count": [p.tweet_count for p in history],
            "goal":  [p.is_goal_event for p in history],
        })
        df["dt"] = pd.to_datetime(df["time"], unit="s")

        latest = df["score"].iloc[-1]
        avg    = df["score"].mean()
        total  = int(df["count"].sum())
        goals  = len(goal_timestamps)

        # KPIs
        def card(label, value, color):
            return html.Div(style={"backgroundColor": C_CARD, "borderRadius": "12px",
                                   "padding": "16px 20px", "flex": "1",
                                   "borderLeft": f"4px solid {color}"}, children=[
                html.P(label, style={"color": C_NEU, "margin": 0, "fontSize": "12px", "textTransform": "uppercase"}),
                html.P(value, style={"color": C_TEXT, "margin": "4px 0 0", "fontSize": "28px", "fontWeight": 600}),
            ])

        kpis = [
            card("Latest batch",  f"{latest:+.2f}", _sentiment_color(latest)),
            card("Match avg",     f"{avg:+.2f}",    _sentiment_color(avg)),
            card("Total comments", f"{total:,}",    C_NEU),
            card("Goal events",   str(goals),        C_GOAL),
        ]

        # Timeline
        timeline = go.Figure()
        timeline.add_trace(go.Scatter(
            x=df["dt"], y=df["score"], mode="lines", fill="tozeroy",
            line=dict(color=C_POS if avg >= 0 else C_NEG, width=2),
            fillcolor=f"rgba({'34,197,94' if avg >= 0 else '239,68,68'},0.12)",
            hovertemplate="%{x|%H:%M:%S}<br>Score: %{y:.2f}<extra></extra>",
        ))
        timeline.add_hline(y=0, line_dash="dot", line_color=C_GRID, line_width=1)
        for ts in goal_timestamps:
            import pandas as pd2
            dt_goal = pd.Timestamp(ts, unit="s")
            timeline.add_vline(x=dt_goal.timestamp()*1000, line_color=C_GOAL,
                               line_dash="dash", line_width=2,
                               annotation_text="⚽ GOAL", annotation_font_color=C_GOAL)
        timeline.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=C_TEXT), height=300,
            margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
            xaxis=dict(gridcolor=C_GRID, zerolinecolor=C_GRID, color=C_NEU),
            yaxis=dict(gridcolor=C_GRID, zerolinecolor=C_GRID, color=C_NEU,
                       range=[-1.1, 1.1], tickvals=[-1, -0.5, 0, 0.5, 1]),
        )

        # Donut
        n_pos = (df["score"] >  0.15).sum()
        n_neu = ((df["score"] >= -0.15) & (df["score"] <= 0.15)).sum()
        n_neg = (df["score"] < -0.15).sum()
        dist = go.Figure(go.Pie(
            labels=["Positive", "Neutral", "Negative"],
            values=[n_pos, n_neu, n_neg],
            marker_colors=[C_POS, C_NEU, C_NEG],
            hole=0.55, textinfo="percent",
        ))
        dist.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font=dict(color=C_TEXT), height=220,
                           margin=dict(l=0, r=0, t=0, b=0))

        # Volume bar
        volume = go.Figure(go.Bar(
            x=df["dt"], y=df["count"],
            marker_color=[C_GOAL if g else C_NEU for g in df["goal"]],
            hovertemplate="%{x|%H:%M:%S}<br>Comments: %{y}<extra></extra>",
        ))
        volume.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=C_TEXT), height=220,
            margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
            xaxis=dict(gridcolor=C_GRID, color=C_NEU),
            yaxis=dict(gridcolor=C_GRID, color=C_NEU),
        )

        return kpis, timeline, dist, volume

    return app