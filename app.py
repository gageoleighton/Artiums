import base64
import io
import tempfile
import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go
import pandas as pd

from pycorn import pc_res3, pc_uni6

app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(
    style={"width": "90%", "margin": "auto"},
    children=[
        html.H2("AKTA FPLC Chromatogram Viewer"),

        dcc.Upload(
            id="upload-raw",
            children=html.Div([
                "Drag and drop AKTA file or ",
                html.A("select a file")
            ]),
            style={
                "width": "100%",
                "height": "80px",
                "lineHeight": "80px",
                "borderWidth": "2px",
                "borderStyle": "dashed",
                "borderRadius": "5px",
                "textAlign": "center"
            },
            multiple=False
        ),

        dcc.Dropdown(
            id="channel-select",
            placeholder="Select chromatogram channel",
        ),

        dcc.Graph(id="chromatogram")
    ]
)

def parse_akta_file(contents, filename):
    """
    Decode uploaded file and parse with PyCORN
    """
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)

    # PyCORN expects a file path → write temp file
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(decoded)
        tmp_path = tmp.name

    try:
        if (tmp_path[-3:]).lower() == "zip":
            fdata = pc_uni6(tmp_path)
            run = fdata.load()
            fdata.xml_parse()
            fdata.clean_up()
        if (tmp_path[-3:]).lower() == "res":
            fdata = pc_res3(tmp_path, reduce = args.reduce, inj_sel=args.inject)
            run = fdata.load()
    except:
        ImportError
        print("Import Error")
    

    chromatograms = {}

    for chrom in run.chromatograms:
        df = pd.DataFrame({
            "x": chrom.x,
            "y": chrom.y
        })
        chromatograms[chrom.name] = df

    return chromatograms

@app.callback(
    Output("channel-select", "options"),
    Output("channel-select", "value"),
    Input("upload-raw", "contents"),
    State("upload-raw", "filename"),
)
def update_channels(contents, filename):
    if contents is None:
        return [], None

    chromatograms = parse_akta_file(contents, filename)

    options = [
        {"label": name, "value": name}
        for name in chromatograms.keys()
    ]

    # Store data in dcc.Store in real apps
    app.server.chrom_data = chromatograms

    default = options[0]["value"] if options else None
    return options, default

@app.callback(
    Output("chromatogram", "figure"),
    Input("channel-select", "value"),
)
def plot_channel(channel):
    if channel is None:
        return go.Figure()

    df = app.server.chrom_data[channel]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["x"],
            y=df["y"],
            mode="lines",
            name=channel
        )
    )

    fig.update_layout(
        xaxis_title="Volume (mL)",
        yaxis_title=channel,
        template="plotly_white"
    )

    return fig




if __name__ == "__main__":
    app.run_server(debug=True)
