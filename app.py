import dash
from dash import dcc, html
import plotly.express as px
import pandas as pd

# Sample chromatogram-like data
df = pd.DataFrame({
    "Volume (mL)": range(0, 100),
    "UV 280 nm": [0.1 + 0.02 * abs(50 - x) for x in range(0, 100)]
})

app = dash.Dash(__name__)
server = app.server  # IMPORTANT for Render

app.layout = html.Div(
    style={"width": "80%", "margin": "auto"},
    children=[
        html.H2("AKTA Chromatogram Demo"),
        dcc.Graph(
            figure=px.line(
                df,
                x="Volume (mL)",
                y="UV 280 nm",
                title="UV 280 nm vs Volume"
            )
        )
    ]
)

if __name__ == "__main__":
    app.run_server(debug=True)
