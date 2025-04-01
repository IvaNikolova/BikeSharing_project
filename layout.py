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
            html.Div(id='missed-trips-05', style={
                'textAlign': 'center',
                'fontSize': '15px',
                'color': 'crimson',
                'marginBottom': '6px'
            }),
            dcc.Graph(id='map_05_05', style={
                'height': '75vh',
                'border': '1px solid #ccc',
                'padding': '5px'
            }, config={'scrollZoom': True}),
        ], style={'width': '45%', 'display': 'inline-block', 'paddingRight': '5px'}),

        # Map: May 11
        html.Div([
            html.H4("🗓️ May 11th, 2022 (Busiest)", style={'textAlign': 'center'}),
            html.Div(id='missed-trips-11', style={
                'textAlign': 'center',
                'fontSize': '15px',
                'color': 'crimson',
                'marginBottom': '6px'
            }),
            dcc.Graph(id='map_05_11', style={
                'height': '75vh',
                'border': '1px solid #ccc',
                'padding': '5px'
            }, config={'scrollZoom': True}),
        ], style={'width': '45%', 'display': 'inline-block', 'paddingRight': '5px'}),

        # Right: Legend with a title
        html.Div([
            html.H4("Legend", style={'marginBottom': '12px'}),
            html.Div("🟥 Empty", style={'fontSize': '15px', 'marginBottom': '4px'}),
            html.Div("🟧 Low (1–4)", style={'fontSize': '15px', 'marginBottom': '4px'}),
            html.Div("🟩 Healthy (5–10)", style={'fontSize': '15px', 'marginBottom': '4px'}),
            html.Div("🟦 Overstocked", style={'fontSize': '15px', 'marginBottom': '4px'})
        ], style={
            'width': '10%',
            'display': 'inline-block',
            'verticalAlign': 'top',
            'padding': '10px',
            'borderLeft': '1px solid #ccc',
            'marginTop': '15px',
        })
    ])
])
