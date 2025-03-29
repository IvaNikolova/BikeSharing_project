import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import warnings
import os

# To ignore the warning about the Scattermap
warnings.filterwarnings("ignore", category=DeprecationWarning)

# === Simulation Settings ===
REAL_DURATION_MINUTES = 5
SIM_DURATION_REAL_SECONDS = REAL_DURATION_MINUTES * 60
SIM_TOTAL_SECONDS = 24 * 60 * 60  # simulate 24h
SPEED_MULTIPLIER = SIM_TOTAL_SECONDS / SIM_DURATION_REAL_SECONDS # Every real second = 86400 / 300 = 288 seconds of simulation.

# === Load data ===
station_df = pd.read_csv("datasets/all_stations.csv")
trip_dfs = {
    "2022-05-05": pd.read_csv("datasets/all_trips_05_05.csv", parse_dates=["start_time", "end_time"]),
    "2022-05-11": pd.read_csv("datasets/all_trips_05_11.csv", parse_dates=["start_time", "end_time"]),
}

if not os.path.exists("missed_trips.csv"):
    pd.DataFrame(columns=[
        "trip_id", "start_time", "end_time", "start_station_id", "end_station_id", "simulated_day"
    ]).to_csv("datasets/missed_trips.csv", index=False)


# === Global simulation state ===
bike_counts_global = {} # dict of current bikes per station {station_id: bike_count}
last_sim_time_global = {} # to track simulation time for each selected day
pending_returns_global = {} 

# === Dash App ===
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Madrid Bike-Sharing Map Simulation"

app.layout = html.Div([
    html.H2("🚲 Madrid Bike-Sharing Simulation"),
    
    html.Div([
        dcc.Dropdown(
            id='day-selector',
            options=[
                {'label': 'May 5th, 2022', 'value': "2022-05-05"},
                {'label': 'May 11th, 2022 (Busiest)', 'value': "2022-05-11"},
            ],
            value="2022-05-11",
            style={"width": "50%"}
        ),
        html.Div(id='progress-label', style={'margin-bottom': '5px', 'fontSize': '18px'}),
        dbc.Progress(id='progress-bar', value=0, max=100, striped=True, animated=True, style={'height': '25px', 'margin-bottom': '10px'}),
    ], style={'margin-bottom': '10px'}),

    html.Div([
        # Left: Map 
        html.Div([
            dcc.Graph(id='map', style={'height': '80vh', 'width': '100%'}, config={'scrollZoom': True}),
            dcc.Interval(id='interval-component', interval=1000, n_intervals=0, max_intervals=300),
        ], style={'width': '85%', 'display': 'inline-block', 'verticalAlign': 'top'}),

        # Right: Color legend
        html.Div([
            html.H4("Stations Legend", style={'margin-bottom': '15px'}),
            html.Div("🟥 Empty (0 bikes)", style={'color': 'red', 'fontSize': '16px', 'margin-bottom': '10px'}),
            html.Div("🟧 Low (1–4 bikes)", style={'color': 'orange', 'fontSize': '16px', 'margin-bottom': '10px'}),
            html.Div("🟩 Healthy (5–10 bikes)", style={'color': 'green', 'fontSize': '16px', 'margin-bottom': '10px'}),
            html.Div("🟦 Overstocked (>10 bikes)", style={'color': 'blue', 'fontSize': '16px', 'margin-bottom': '10px'}),
            html.Div(id='missed-trips', style={'fontSize': '18px', 'marginTop': '10px'}),
        ], style={'width': '15%', 'display': 'inline-block', 'padding': '15px 20px', 'borderLeft': '1px solid #ccc', 'height': '85vh'})
        
    ])
])

# === Helper functions ===
def get_color(bike_count):
    if bike_count == 0: return "red"
    elif bike_count < 5: return "orange"
    elif 5 <= bike_count <= 10: return "green"
    else: return "blue"

# === Simulation Callback ===
@app.callback(
    [Output('map', 'figure'),
     Output('progress-bar', 'value'),
     Output('progress-label', 'children'),
     Output('missed-trips', 'children')],  
    [Input('interval-component', 'n_intervals'),
     Input('day-selector', 'value')]
)
def update_simulation(n, selected_date_str):
    global bike_counts_global, last_sim_time_global

    trip_df = trip_dfs[selected_date_str]
    sim_date = datetime.strptime(selected_date_str, "%Y-%m-%d")
    current_sim_time = sim_date + timedelta(seconds=n * SPEED_MULTIPLIER)
    
    # Create pending return list if it's the first time
    if selected_date_str not in pending_returns_global:
        pending_returns_global[selected_date_str] = []

    pending_returns = pending_returns_global[selected_date_str]


    # Stations start with 5 bikes and the simulation starts from midnight of the chosen day
    if n == 0 or selected_date_str not in bike_counts_global:
        bike_counts_global[selected_date_str] = {sid: 7 for sid in station_df['station_id']}
        last_sim_time_global[selected_date_str] = sim_date

    bike_counts = bike_counts_global[selected_date_str]
    last_time = last_sim_time_global[selected_date_str]
    
    # Return bikes whose end_time has arrived
    to_return = [trip for trip in pending_returns if trip['end_time'] <= current_sim_time]
    for trip in to_return:
        end_id = trip['end_id']
        bike_counts[end_id] = bike_counts.get(end_id, 0) + 1
        pending_returns.remove(trip)

    new_trips = trip_df[
        (trip_df['start_time'] >= last_time) &
        (trip_df['start_time'] < current_sim_time)
    ]
    
    missed_trips = 0  # initialize missed counter
    missed_trip_rows = []

    for _, trip in new_trips.iterrows():
        start_id = trip['start_station_id']
        end_id = trip['end_station_id']
        end_time = trip['end_time']

        if bike_counts.get(start_id, 0) > 0:
            bike_counts[start_id] -= 1
            pending_returns.append({
                "end_time": end_time,
                "end_id": end_id
            })
        else:
            missed_trips += 1
            missed_trip_rows.append({
                "trip_id": trip['trip_id'],
                "start_time": trip['start_time'],
                "end_time": end_time,
                "start_station_id": start_id,
                "end_station_id": end_id,
                "simulated_day": selected_date_str
            })

    if missed_trip_rows:
        new_df = pd.DataFrame(missed_trip_rows)

        if os.path.exists("datasets/missed_trips.csv"):
            existing_df = pd.read_csv("datasets/missed_trips.csv")

            # Clean up: drop empty or NA-only rows
            existing_df = existing_df.dropna(how="all")
            new_df = new_df.dropna(how="all")

            combined_df = pd.concat([existing_df, new_df]).drop_duplicates(subset=["trip_id", "simulated_day"])
        else:
            combined_df = new_df

        combined_df.to_csv("datasets/missed_trips.csv", index=False)



    last_sim_time_global[selected_date_str] = current_sim_time

    # === Create the map figure ===
    latitudes = []
    longitudes = []
    colors = []
    sizes = []
    hover_texts = []

    for _, row in station_df.iterrows():
        sid = row['station_id']
        lat = row['lat']
        lon = row['lon']
        name = row['station_name']
        count = bike_counts.get(sid, 0)
        color = get_color(count)

        latitudes.append(lat)
        longitudes.append(lon)
        colors.append(color)
        sizes.append(10 + count)  # make size reflect bike count
        hover_texts.append(f"{name}<br>Bikes: {count}")

    fig = go.Figure()

    fig.add_trace(go.Scattermapbox(
        lat=latitudes,
        lon=longitudes,
        mode='markers',
        marker=go.scattermapbox.Marker(size=sizes, color=colors, opacity=0.8),
        text=hover_texts,
        hoverinfo='text',
        name='Stations'
    ))

    fig.update_layout(
        mapbox=dict(
            style="carto-positron",
            center=dict(
                lat=sum(latitudes) / len(latitudes),
                lon=sum(longitudes) / len(longitudes)
            ),
            zoom=12
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        title=f"Date / Time: {selected_date_str} — {current_sim_time.strftime('%H:%M')}",
        showlegend=False
    )

    # Progress bar
    progress_percent = int(min((n / 300) * 100, 100))
    timer_text = f"Progress: {progress_percent}%"

    return fig, progress_percent, timer_text, f"❌ Missed trips: {missed_trips}"


# === Run the app ===
if __name__ == '__main__':
    app.run(debug=True)
