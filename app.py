import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import pandas as pd
import plotly.express as px
import dash_bootstrap_components as dbc
from datetime import datetime, timedelta

# === SETTINGS ===
REAL_DURATION_MINUTES = 5
SIM_DURATION_REAL_SECONDS = REAL_DURATION_MINUTES * 60
SIM_TOTAL_SECONDS = 24 * 60 * 60  # 24 hours
SPEED_MULTIPLIER = SIM_TOTAL_SECONDS / SIM_DURATION_REAL_SECONDS

# === Load station data ===
station_df = pd.read_csv("datasets/all_stations.csv")

# === Load trip data ===
trip_dfs = {
    "2022-05-05": pd.read_csv("datasets/all_trips_05_05.csv", parse_dates=["start_time", "end_time"]),
    "2022-05-11": pd.read_csv("datasets/all_trips_05_11.csv", parse_dates=["start_time", "end_time"])
}

# === Dash App ===
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Madrid Bike Simulation"

app.layout = html.Div([
    html.H1("🚲 Madrid Bike Activity Simulation"),

    html.Label("Select a day to simulate:", style={"margin-top": "10px"}),
    dcc.Dropdown(
        id='day-selector',
        options=[
            {'label': 'May 5th, 2022', 'value': "2022-05-05"},
            {'label': 'May 11th, 2022 (Busiest)', 'value': "2022-05-11"},
        ],
        value="2022-05-05",
        clearable=False,
        style={'width': '50%'}
    ),

    html.Div([
        html.Div(id='progress-label', style={
            'margin-top': '10px',
            'font-weight': 'bold',
            'font-size': '20px',
            'color': '#0074D9'
        }),
        dbc.Progress(id='progress-bar', value=0, max=100, striped=True, animated=True, style={'height': '25px'}),
        html.Div(id='simulation-done-msg', style={
            'margin-top': '15px',
            'font-weight': 'bold',
            'font-size': '24px',
            'color': 'green'
        })
    ]),

    html.Div([
        html.Div("🟨 < 5 bikes", style={'color': '#ffce1b', 'display': 'inline-block', 'margin-right': '20px'}),
        html.Div("🟩 5–10 bikes", style={'color': 'green', 'display': 'inline-block', 'margin-right': '20px'}),
        html.Div("🟥 > 10 bikes", style={'color': 'red', 'display': 'inline-block'}),
    ], style={'margin-top': '10px', 'margin-bottom': '10px', 'font-weight': 'bold', 'font-size': '16px'}),

    dcc.Graph(id='map-graph'),
    dcc.Interval(id='interval-component', interval=1000, n_intervals=0, max_intervals=300)
])

@app.callback(
    [Output('map-graph', 'figure'),
     Output('progress-bar', 'value'),
     Output('progress-label', 'children'),
     Output('simulation-done-msg', 'children')],
    [Input('interval-component', 'n_intervals'),
     Input('day-selector', 'value')]
)
def update_simulation(n, selected_date_str):
    if n > 300:
        raise dash.exceptions.PreventUpdate

    trip_df = trip_dfs[selected_date_str]
    sim_date = datetime.strptime(selected_date_str, "%Y-%m-%d")
    current_sim_time = sim_date + timedelta(seconds=n * SPEED_MULTIPLIER)

    active_trips = trip_df[(trip_df['start_time'] <= current_sim_time) & (trip_df['end_time'] > current_sim_time)]
    bikes_per_station = active_trips['start_station_id'].value_counts().to_dict()

    df_plot = station_df.copy()
    df_plot['bike_count'] = df_plot['station_id'].map(bikes_per_station).fillna(0)

    def get_color(bike_count):
        if bike_count < 5:
            return 'yellow'
        elif 5 <= bike_count <= 10:
            return 'green'
        else:
            return 'red'

    df_plot['color'] = df_plot['bike_count'].apply(get_color)

    fig = px.scatter_map(
        df_plot,
        lat="lat",
        lon="lon",
        color="color",
        color_discrete_map={'yellow': '#ffce1b', 'green': 'green', 'red': 'red'},
        zoom=12,
        height=800,
        hover_name="station_name"
    )

    fig.update_traces(
        marker=dict(size=10, opacity=0.9),
        customdata=df_plot[['bike_count']],
        hovertemplate="%{hovertext}<br><br>Bikes: %{customdata[0]}/10<extra></extra>"
    )

    fig.update_layout(
        showlegend=False,
        mapbox_style="open-street-map",
        mapbox_center={"lat": 40.4168, "lon": -3.7038},
        margin={"r": 0, "t": 40, "l": 0, "b": 0},
        title=f"Simulated: {selected_date_str} — {current_sim_time.strftime('%H:%M')}"
    )

    progress_percent = int(min((n / 300) * 100, 100))
    time_left = max(300 - n, 0)
    mins, secs = divmod(time_left, 60)
    timer_text = f"Simulation Progress: {progress_percent}% — Time Left: {mins:02}:{secs:02}"
    done_message = "✅ Simulation Complete!" if n >= 300 else ""

    return fig, progress_percent, timer_text, done_message

if __name__ == '__main__':
    app.run(debug=True)
