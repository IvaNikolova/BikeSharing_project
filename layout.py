from dash import dcc, html
import dash_bootstrap_components as dbc

layout = html.Div([
    html.H2("🚲 Madrid Bike-Sharing Simulation", style={
        'textAlign': 'center',
        'marginBottom': '20px'
    }),

    html.Div([
        # Left: Date and progress bar
        html.Div([
            html.Div(id='current-time', style={'fontSize': '16px', 'marginBottom': '6px', 'fontWeight': 'bold'}),
            html.Div(id='progress-label', style={'fontSize': '14px', 'marginBottom': '5px'}),
            dbc.Progress(id='progress-bar', value=0, max=100, striped=True, animated=True,
                         style={'height': '12px', 'marginBottom': '8px'})
        ], style={
            'width': '25%',
            'display': 'inline-block',
            'verticalAlign': 'top',
            'padding': '10px'
        }),

        # Spacer (centered title already exists)
        html.Div([], style={'width': '75%', 'display': 'inline-block'}),
    ], style={'marginBottom': '10px'}),

    dcc.Interval(id='interval-component', interval=1000, n_intervals=0, max_intervals=300),

    html.Div([
        # Map: May 5
        html.Div([
            html.H4("🗓️ May 5th, 2022", style={'textAlign': 'center'}),
            html.Div(id='missed-trips-05', style={'textAlign': 'center', 'fontSize': '15px', 'color': 'crimson', 'marginBottom': '6px'}),
            html.Div(id='summary-left', style={'textAlign': 'center', 'marginTop': '10px', 'fontSize': '15px'}),
            dcc.Graph(id='map_05_05', style={'height': '75vh', 'border': '1px solid #ccc', 'padding': '5px'}, config={'scrollZoom': True}),
        ], style={'width': '45%', 'display': 'inline-block', 'paddingRight': '5px'}),

        # Map: May 11
        html.Div([
            html.H4("🗓️ May 11th, 2022 (Busiest)", style={'textAlign': 'center'}),
            html.Div(id='missed-trips-11', style={'textAlign': 'center', 'fontSize': '15px', 'color': 'crimson', 'marginBottom': '6px'}),
            html.Div(id='summary-right', style={'textAlign': 'center', 'marginTop': '10px', 'fontSize': '15px'}),
            dcc.Graph(id='map_05_11', style={'height': '75vh', 'border': '1px solid #ccc', 'padding': '5px'}, config={'scrollZoom': True}),
        ], style={'width': '45%', 'display': 'inline-block', 'paddingRight': '5px'}),

        # Right: Legend with a title
        html.Div([
            html.H5("Legend", style={"margin-bottom": "10px"}),
        html.Div([
            html.Div([
                html.Span(style={
                    "display": "inline-block",
                    "width": "12px",
                    "height": "12px",
                    "borderRadius": "50%",
                    "backgroundColor": "red",
                    "marginRight": "8px"
                }),
                html.Span("Empty")
            ], style={"marginBottom": "6px"}),

            html.Div([
                html.Span(style={
                    "display": "inline-block",
                    "width": "12px",
                    "height": "12px",
                    "borderRadius": "50%",
                    "backgroundColor": "orange",
                    "marginRight": "8px"
                }),
                html.Span("Low (1–15)")
            ], style={"marginBottom": "6px"}),

            html.Div([
                html.Span(style={
                    "display": "inline-block",
                    "width": "12px",
                    "height": "12px",
                    "borderRadius": "50%",
                    "backgroundColor": "green",
                    "marginRight": "8px"
                }),
                html.Span("Healthy (16–30)")
            ], style={"marginBottom": "6px"}),

            html.Div([
                html.Span(style={
                    "display": "inline-block",
                    "width": "12px",
                    "height": "12px",
                    "borderRadius": "50%",
                    "backgroundColor": "blue",
                    "marginRight": "8px"
                }),
                html.Span("Overstocked")
            ], style={"marginBottom": "6px"}),
        ])
        ], style={
            'width': '10%',
            'display': 'inline-block',
            'verticalAlign': 'top',
            'padding': '10px',
            'borderLeft': '1px solid #ccc',
            'marginTop': '15px',
        }),
        
        html.H3("MARL Redistribution Simulation", style={'textAlign': 'center', 'marginTop': '40px'}),

        html.Div([
            html.Div([
                html.H4("🗓️ May 5th, 2022 (MARL)", style={'textAlign': 'center'}),
                html.Div(id='missed-trips-marl-05', style={'textAlign': 'center', 'fontSize': '15px', 'color': 'crimson', 'marginBottom': '6px'}),
                html.Div(id='summary-marl-left', style={'textAlign': 'center', 'marginTop': '10px', 'fontSize': '15px'}),
                dcc.Graph(id='map_marl_05_05', style={'height': '75vh', 'border': '1px solid #ccc', 'padding': '5px'}, config={'scrollZoom': True}),
            ], style={'width': '45%', 'display': 'inline-block', 'paddingRight': '5px' }),

            html.Div([
                html.H4("🗓️ May 11th, 2022 (MARL)", style={'textAlign': 'center'}),
                html.Div(id='missed-trips-marl-11', style={'textAlign': 'center', 'fontSize': '15px', 'color': 'crimson', 'marginBottom': '6px'}),
                html.Div(id='summary-marl-right', style={'fontSize': '14px', 'textAlign': 'center', 'marginTop': '10px'}),
                dcc.Graph(id='map_marl_05_11', style={'height': '75vh', 'padding': '5px', 'border': '1px solid #ccc'}, config={'scrollZoom': True}),
            ], style={'width': '45%', 'display': 'inline-block', 'paddingRight': '5px'}),
        ])
        
    ])
])


