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
station_df['lat'] = pd.to_numeric(station_df['lat'], errors='coerce')
station_df['lon'] = pd.to_numeric(station_df['lon'], errors='coerce')
station_df = station_df.dropna(subset=['lat', 'lon'])  # Drop stations with missing coords

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
last_processed_frame_global = {}

# === Dash App ===
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
app.title = "Madrid Bike-Sharing Map Simulation"

app.layout = html.Div([
    html.H2("🚲 Madrid Bike-Sharing Simulation"),
    dcc.Interval(id='interval-component', interval=1000, n_intervals=0, max_intervals=300),

    html.Div([
        html.Div([
            html.H4("Stations Legend", style={'margin-bottom': '15px'}),
            html.Div("🟥 Empty (0 bikes) | 🟧 Low (1–4 bikes) | 🟩 Healthy (5–10 bikes) | 🟦 Overstocked (>10 bikes) ", style={'color': 'black', 'fontSize': '16px', 'margin-bottom': '10px'}),
        ], style={'width': '115%', 'display': 'inline-block', 'padding': '15px 20px', 'borderLeft': '1px solid #ccc'}),
        html.Div(id='progress-label', style={'margin-bottom': '5px', 'fontSize': '18px'}),
        dbc.Progress(id='progress-bar', value=0, max=100, striped=True, animated=True, style={'height': '25px', 'margin-bottom': '10px'}),
    ], style={'margin-bottom': '10px'}),

    html.Div([
        # Map 1: May 5
        html.Div([
            html.H4("🗓️ May 5th, 2022", style={'textAlign': 'center'}),
            dcc.Graph(id='map_05_05', style={'height': '80vh'}, config={'scrollZoom': True}),
            html.Div(id='missed-trips-05', style={'fontSize': '16px', 'textAlign': 'center', 'marginTop': '10px'}),
        ], style={'width': '50%', 'display': 'inline-block'}),

        # Map 2: May 11
        html.Div([
            html.H4("🗓️ May 11th, 2022 (Busiest)", style={'textAlign': 'center'}),
            dcc.Graph(id='map_05_11', style={'height': '80vh'}, config={'scrollZoom': True}),
            html.Div(id='missed-trips-11', style={'fontSize': '16px', 'textAlign': 'center', 'marginTop': '10px'}),
        ], style={'width': '50%', 'display': 'inline-block'}),
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
    [Output('map_05_05', 'figure'),
     Output('map_05_11', 'figure'),
     Output('progress-bar', 'value'),
     Output('progress-label', 'children'),
     Output('missed-trips-05', 'children'),
     Output('missed-trips-11', 'children')],
    Input('interval-component', 'n_intervals')
)
def update_dual_simulation(n):
    results = []
    for selected_date_str in ["2022-05-05", "2022-05-11"]:
        global bike_counts_global, last_sim_time_global

        # Prevent duplicate interval processing
        if selected_date_str not in last_processed_frame_global:
            last_processed_frame_global[selected_date_str] = -1

        if n <= last_processed_frame_global[selected_date_str]:
            raise dash.exceptions.PreventUpdate

        last_processed_frame_global[selected_date_str] = n

        trip_df = trip_dfs[selected_date_str]
        sim_date = datetime.strptime(selected_date_str, "%Y-%m-%d")
        current_sim_time = sim_date + timedelta(seconds=n * SPEED_MULTIPLIER)
        
        # Create pending return list if it's the first time
        if selected_date_str not in pending_returns_global:
            pending_returns_global[selected_date_str] = []

        pending_returns = pending_returns_global[selected_date_str]

        # Stations start with 5 bikes and the simulation starts from midnight of the chosen day
        if n == 0 or selected_date_str not in bike_counts_global:
            # Reset missed trips CSV
            with open("datasets/missed_trips.csv", "w") as f:
                f.write("")  # clears the file

            # Reset bikes and timer
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
        
        missed_trip_rows = []

        for _, trip in new_trips.iterrows():
            start_id = trip['start_station_id']
            end_id = trip['end_station_id']
            end_time = trip['end_time']

            # Trip is being attempted now — only then we check
            if bike_counts.get(start_id, 0) > 0:
                # Proceed with trip
                bike_counts[start_id] -= 1
                pending_returns.append({
                    "end_time": end_time,
                    "end_id": end_id
                })
            else:
                # Start station has no bikes = missed trip!
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

            if not new_df.empty:
                new_df.to_csv("datasets/missed_trips.csv", mode='a', header=not os.path.exists("datasets/missed_trips.csv"), index=False)

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
        results.extend([fig, f"❌ Missed trips: {len(missed_trip_rows)}"])

    # Progress bar
    progress_percent = int(min((n / 300) * 100, 100))
    timer_text = f"Progress: {progress_percent}%"

    return (results[0], results[2], progress_percent, timer_text, results[1], results[3])

# === Run the app ===
if __name__ == '__main__':
    app.run(debug=True)