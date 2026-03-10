import base64
import io, pprint
import tempfile
import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go
import pandas as pd

from pycorn import pc_res3, pc_uni6

app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(
    style={
        "width": "90%",
        "margin": "auto",
        "height": "100vh",
        "display": "flex",
        "flexDirection": "column",
    },
    children=[
        html.H2("AKTA FPLC Chromatogram Viewer"),
        # client-side store for chromatogram data (persists in browser localStorage)
        dcc.Store(id="chrom-store", storage_type="local"),
        dcc.Upload(
            id="upload-raw",
            children=html.Div(["Drag and drop AKTA file or ", html.A("select a file")]),
            style={
                "width": "100%",
                "height": "80px",
                "lineHeight": "80px",
                "borderWidth": "2px",
                "borderStyle": "dashed",
                "borderRadius": "5px",
                "textAlign": "center",
            },
            multiple=False,
        ),
        html.Div(
            style={
                "display": "flex",
                "gap": "12px",
                "alignItems": "stretch",
                "flex": "1 1 auto",
                "minHeight": 0,
            },
            children=[
                html.Div(
                    style={
                        "flex": "0 0 20%",
                        "maxWidth": "20%",
                        "boxSizing": "border-box",
                        "paddingRight": "8px",
                        "overflowY": "auto",
                    },
                    children=[
                        html.Div(
                            "Channels",
                            style={"fontWeight": "600", "marginBottom": "6px"},
                        ),
                        dcc.Checklist(
                            id="channel-select",
                            options=[],
                            value=[],
                            inputStyle={"margin-right": "6px", "margin-left": "10px"},
                            labelStyle={"display": "block"},
                        ),
                    ],
                ),
                html.Div(
                    style={
                        "flex": "1 1 80%",
                        "maxWidth": "80%",
                        "boxSizing": "border-box",
                        "minHeight": 0,
                        "display": "flex",
                    },
                    children=[
                        dcc.Graph(
                            id="chromatogram", style={"height": "100%", "width": "100%"}
                        )
                    ],
                ),
            ],
        ),
    ],
)


def parse_akta_file(contents, filename):
    """
    Decode uploaded file and parse with PyCORN
    """
    content_type, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)

    # PyCORN expects a file path → write temp file
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(decoded)
        tmp_path = tmp.name

    try:
        run = None

        # prefer the uploaded filename to determine file type
        ext = (filename or "").split(".")[-1].lower()

        if ext == "zip":
            try:
                fdata = pc_uni6(tmp_path)
                fdata.load()
                # xml_parse/clean_up may be optional; ignore failures but log
                try:
                    fdata.xml_parse()
                    fdata.clean_up()
                    run = fdata
                except Exception:
                    pass
            except Exception as e:
                print("pc_uni6 parse error:", e)

        elif ext == "res":
            try:
                # call with minimal required args; avoid using undefined `args`
                fdata = pc_res3(tmp_path)
                run = fdata.load()
            except Exception as e:
                print("pc_res3 parse error:", e)
    except Exception as e:
        print("Unexpected parse error:", e)

    # with open("run.txt", "w") as f:
    #     f.write(pprint.pformat(run))

    # If parsing failed, return empty result
    chromatograms = {}
    if run is None:
        print("Failed to parse AKTA file")
        return chromatograms

    for name, chrom in run.items():
        try:
            df = pd.DataFrame(
                {"x": [p[0] for p in chrom["data"]], "y": [p[1] for p in chrom["data"]]}
            )
            chromatograms[name] = df
        except Exception:
            # skip malformed chromatograms
            print("Malformed chromatogram:", name)
            continue

    return chromatograms


@app.callback(
    Output("channel-select", "options"),
    Output("channel-select", "value"),
    Output("chrom-store", "data"),
    Input("upload-raw", "contents"),
    State("upload-raw", "filename"),
)
def update_channels(contents, filename):
    if contents is None:
        # # use the Example file
        # with open("Example_HisTrap_HP_5mL.zip", "r") as f:
        #     contents = f.read()
        # filename = "example_chromatogram.txt"
        return [], None, None

    chromatograms = parse_akta_file(contents, filename)

    options = [{"label": name, "value": name} for name in chromatograms.keys()]

    # keep a server-side pointer (fast for server-only ops)
    app.server.chrom_data = chromatograms

    # serialize chromatogram DataFrames for client-side storage (JSON-serializable)
    serialized = {
        name: {"x": df["x"].tolist(), "y": df["y"].tolist()}
        for name, df in chromatograms.items()
    }

    # default-select chromatograms whose names start with "UV"
    uv_defaults = [
        opt["value"] for opt in options if opt["value"].upper().startswith("UV")
    ]
    if not uv_defaults and options:
        uv_defaults = [options[0]["value"]]

    return options, uv_defaults, serialized


@app.callback(
    Output("chromatogram", "figure"),
    Input("channel-select", "value"),
    State("chrom-store", "data"),
    State("upload-raw", "filename"),
)
def plot_channel(channels, store_data, filename):
    # `channels` is a list of selected channel names from the Checklist
    if not channels:
        return go.Figure()

    fig = go.Figure()

    # Add title to the figure
    fig.update_layout(title=filename, title_x=0.5)

    # determine available keys to find UV channels (prefer server-side)
    available_keys = []
    if hasattr(app.server, "chrom_data") and getattr(app.server, "chrom_data"):
        available_keys = list(getattr(app.server, "chrom_data").keys())
    elif store_data:
        available_keys = list(store_data.keys())

    uv_keys = [k for k in available_keys if k.upper().startswith("UV 1_")]
    last_uv = uv_keys[-1] if uv_keys else None
    for channel in channels:
        # Prefer server-side data when available (faster, avoids deserialization)
        if hasattr(app.server, "chrom_data") and channel in getattr(
            app.server, "chrom_data"
        ):
            df = app.server.chrom_data[channel]
            x = df["x"]
            y = df["y"]
        else:
            # fallback to client-side stored data (from dcc.Store)
            if not store_data or channel not in store_data:
                # skip missing channel
                continue
            x = store_data[channel]["x"]
            y = store_data[channel]["y"]

        # decide if this is a UV trace (primary y) or non-UV (secondary y)
        is_uv = channel.upper().startswith("UV")

        # choose color for some UV channels if present
        color_dic = {
            "280": "blue",
            "260": "red",
            "214": "orange",
            "320": "purple",
            "Conc B": "green",
        }
        color = None
        parts = channel.replace(" ", "_").split("_")
        if len(parts) >= 2 and parts[-1].isdigit():
            color = color_dic.get(parts[-1])
        elif channel.upper() == "CONC B":
            color = color_dic.get("Conc B")

        trace_kwargs = {"x": x, "y": y, "mode": "lines", "name": channel}
        if color:
            trace_kwargs["line"] = {"color": color}

        if is_uv:
            fig.add_trace(go.Scatter(**trace_kwargs))
        else:
            # plot on secondary y-axis
            trace_kwargs["yaxis"] = "y2"
            fig.add_trace(go.Scatter(**trace_kwargs))

    fig.update_layout(
        xaxis_title="Volume (mL)",
        template="plotly_white",
        yaxis=dict(title="UV"),
        yaxis2=dict(title="Other", overlaying="y", side="right"),
    )
    return fig


if __name__ == "__main__":
    app.run(debug=True)
