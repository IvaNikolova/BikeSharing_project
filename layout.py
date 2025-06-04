# c165dee5-8a1c-4dc2-90de-a4e0733d073f.py

from dash import dcc, html
import dash_bootstrap_components as dbc

layout = html.Div(
    # ───── Top‐Level Wrapper: dark page bg, light text by default ─────
    style={
        "backgroundColor": "#052761",    # dark‐blue/charcoal page bg
        "padding": "0 20px",
        "paddingBottom": "30px" 
    },
    children=[

        # ───── 1) MAIN TITLE (outside of any panel) ─────
        html.H2(
            "🚲 Madrid Bike-Sharing Simulation",
            style={"textAlign": "center", "paddingTop": "30px", "paddingBottom": "30px", "color": "#FFFFFF", "fontWeight": "bold", "fontSize": "32px" }
        ),

        dcc.Interval(
            id="interval-component",
            interval=1000,     # 1 second
            n_intervals=0,
            max_intervals=300  # stops after 300 ticks
        ),

        # ───── 2) “May 5th, 2022” PANEL ─────
        html.Div(
            id="panel-may-5",
            style={"backgroundColor": "#1E1E1E", "border": "1px solid #333333", "borderRadius": "8px", "padding": "15px", "marginBottom": "40px", "width" : "85%"},
            children=[
                # a) Time + Progress Bar (only needs to appear once, at top of May 5th box)
                 html.Div(
                    id="current-time",
                    style={"width": "100%", "fontSize": "18px", "fontWeight": "bold", "color": "#FFFFFF", "marginBottom": "8px","textAlign": "center"}
                ),
                
                html.Div(
                    children=dbc.Progress(
                        id="progress-bar",
                        value=0,
                        max=100,
                        striped=True,
                        animated=True,
                        style={"height": "14px", "width": "100%"}
                    ),
                    style={"marginBottom": "25px"}
                ),
            
                # b) Two maps side by side
                html.Div(
                    style={"display": "flex", "alignItems": "flex-start", "gap": "2%"},
                    children=[
                        # ‣ Left: “May 5th, 2022” (Regular)
                        html.Div(
                            style={"flex": "1", "display": "flex", "flexDirection": "column", "backgroundColor": "#1E1E1E"},
                            children=[
                                html.H4(
                                    "🗓️ May 5th, 2022",
                                    style={"textAlign": "center", "color": "#FFFFFF", "marginBottom": "8px"}
                                ),
                                html.Div(
                                    id="missed-trips-05",
                                    style={"textAlign": "center", "fontSize": "15px", "color": "crimson", "marginBottom": "6px"}
                                ),
                                html.Div(
                                    id="summary-left",
                                    style={"textAlign": "center", "marginBottom": "10px", "fontSize": "15px", "color": "#DDDDDD"}
                                ),
                                dcc.Graph(
                                    id="map_05_05",
                                    style={"width": "100%", "height": "600px", "backgroundColor": "transparent", "border": "none"},
                                    config={"scrollZoom": True, "displayModeBar": False }
                                )
                            ]
                        ),

                        # ‣ Right: “May 5th, 2022 (MARL)”
                        html.Div(
                            style={"flex": "1", "display": "flex", "flexDirection": "column", "backgroundColor": "#1E1E1E"},
                            children=[
                                html.H4(
                                    "🗓️ May 5th, 2022 (MARL)",
                                    style={"textAlign": "center", "color": "#FFFFFF", "marginBottom": "8px"}
                                ),
                                html.Div(
                                    id="missed-trips-marl-05",
                                    style={"textAlign": "center", "fontSize": "15px", "color": "crimson", "marginBottom": "6px"}
                                ),
                                html.Div(
                                    id="summary-marl-left",
                                    style={"textAlign": "center", "marginBottom": "10px", "fontSize": "15px", "color": "#DDDDDD"}
                                ),
                                dcc.Graph(
                                    id="map_marl_05_05",
                                    style={"width": "100%", "height": "600px", "backgroundColor": "transparent", "border": "none"},
                                    config={"scrollZoom": True, "displayModeBar": False }
                                )
                            ]
                        ),
                    ]
                )
            ]
        ),


        # ───── 3) “May 11th, 2022” PANEL ─────
        html.Div(
            id="panel-may-11",
            style={"backgroundColor": "#1E1E1E", "border": "1px solid #333333", "borderRadius": "8px", "padding": "15px", "width" : "85%"},
            children=[
                # b) Two maps side by side
                html.Div(
                    style={"display": "flex", "alignItems": "flex-start", "gap":"2%"},
                    children=[
                        # ‣ Left: “May 11th, 2022” (Regular)
                        html.Div(
                            style={"flex": "1", "display": "flex", "flexDirection": "column", "backgroundColor": "#1E1E1E"},
                            children=[
                                html.H4(
                                    "🗓️ May 11th, 2022",
                                    style={"textAlign": "center", "color": "#FFFFFF", "marginBottom": "8px"}
                                ),
                                html.Div(
                                    id="missed-trips-11",
                                    style={"textAlign": "center", "fontSize": "15px", "color": "crimson", "marginBottom": "6px"}
                                ),
                                html.Div(
                                    id="summary-right",
                                    style={"textAlign": "center", "marginBottom": "10px", "fontSize": "15px", "color": "#DDDDDD"}
                                ),
                                dcc.Graph(
                                    id="map_05_11",
                                    style={"width": "100%", "height": "600px", "backgroundColor": "transparent", "border": "none"},
                                    config={"scrollZoom": True, "displayModeBar": False }
                                )
                            ]
                        ),


                        # ‣ Right: “May 11th, 2022 (MARL)”
                        html.Div(
                            style={"flex": "1", "display": "flex", "flexDirection": "column", "backgroundColor": "#1E1E1E"},
                            children=[
                                html.H4(
                                    "🗓️ May 11th, 2022 (MARL)",
                                    style={"textAlign": "center", "color": "#FFFFFF", "marginBottom": "8px"}
                                ),
                                html.Div(
                                    id="missed-trips-marl-11",
                                    style={"textAlign": "center", "fontSize": "15px", "color": "crimson", "marginBottom": "6px"}
                                ),
                                html.Div(
                                    id="summary-marl-right",
                                    style={"textAlign": "center", "marginBottom": "10px", "fontSize": "15px", "color": "#DDDDDD"}
                                ),
                                dcc.Graph(
                                    id="map_marl_05_11",
                                    style={"width": "100%", "height": "600px", "backgroundColor": "transparent", "border": "none"},
                                    config={"scrollZoom": True, "displayModeBar": False }
                                )
                            ]
                        ),
                    ]
                )
            ]
        ),


        # ───── 4) STICKY LEGEND (always visible, on the right) ─────
        html.Div(
            id="legend-container",
            style={"position": "fixed", "top": "30px", "right": "30px", "width": "200px", "backgroundColor": "#1E1E1E", "border": "1px solid #333333", "borderRadius": "6px", "padding": "12px","zIndex": "999"},
            children=[
                html.H5("Legend", style={"color": "#FFFFFF", "marginBottom": "10px", "fontSize": "18px"}),

                html.Div(
                    children=[
                        html.Div(
                            style={"display": "flex", "alignItems": "center", "marginBottom": "8px"},
                            children=[
                                html.Span(style={"display": "inline-block", "width": "14px", "height": "14px", "borderRadius": "50%", "backgroundColor": "red", "marginRight": "8px"}),
                                html.Span("Empty", style={"color": "#EEEEEE", "fontSize": "15px"})
                            ]
                        ),
                        html.Div(
                            style={"display": "flex", "alignItems": "center", "marginBottom": "8px"},
                            children=[
                                html.Span(style={"display": "inline-block", "width": "14px", "height": "14px", "borderRadius": "50%", "backgroundColor": "orange", "marginRight": "8px"}),
                                html.Span("Low (1–15)", style={"color": "#EEEEEE", "fontSize": "15px"})
                            ]
                        ),
                        html.Div(
                            style={"display": "flex", "alignItems": "center", "marginBottom": "8px"},
                            children=[
                                html.Span(style={"display": "inline-block", "width": "14px", "height": "14px", "borderRadius": "50%", "backgroundColor": "green", "marginRight": "8px"}),
                                html.Span("Healthy (16–30)", style={"color": "#EEEEEE", "fontSize": "15px"})
                            ]
                        ),
                        html.Div(
                            style={"display": "flex", "alignItems": "center"},
                            children=[
                                html.Span(style={"display": "inline-block","width": "14px","height": "14px","borderRadius": "50%", "backgroundColor": "blue", "marginRight": "8px"}),
                                html.Span("Overstocked", style={"color": "#EEEEEE", "fontSize": "15px"})
                            ]
                        ),
                    ]
                )
            ]
        )
    ]
)
