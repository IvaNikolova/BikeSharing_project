import dash
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from layout import layout
import warnings
import os

# Append a DataFrame to a CSV, and include the header if the file is missing or empty.
def append_df_with_header_check(df, path):
    write_header = not os.path.exists(path) or os.stat(path).st_size == 0
    df.to_csv(path, mode='a', header=write_header, index=False)

# To ignore the warning about the Scattermap
warnings.filterwarnings("ignore", category=DeprecationWarning)

# === Simulation Settings ===
REAL_DURATION_MINUTES = 5
SIM_DURATION_REAL_SECONDS = REAL_DURATION_MINUTES * 60
SIM_TOTAL_SECONDS = 24 * 60 * 60  # simulate 24h
SPEED_MULTIPLIER = SIM_TOTAL_SECONDS / SIM_DURATION_REAL_SECONDS # Every real second = 86400 / 300 = 288 seconds of simulation.

# Thresholds based on May 5th analysis
BUSY_THRESHOLD = 122.94 + 48.96    # ≈ 188
UNDERUSED_THRESHOLD = 122.94 - 48.96    # ≈ 58

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
stations_global = {} #  dict of current bikes per station {station_id: bike_count}
in_transit_bikes_global = {} # bikes currently being used, scheduled to return at end_time
last_update_time_global = {} # last simulation time processed per date
last_frame_global = {} # last Dash frame (n) processed per date

# === Dash App ===
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
app.title = "Madrid Bike-Sharing Map Simulation"
app.layout = layout

# === Helper functions ===
def get_color(bike_count):
    if bike_count == 0: return "red"
    elif bike_count <= 15: return "orange"
    elif 15 < bike_count <= 30: return "green"
    else: return "blue"

# === Simulation Callback ===
@app.callback(
    [Output('map_05_05', 'figure'),
     Output('map_05_11', 'figure'),
     Output('progress-bar', 'value'),
     Output('progress-label', 'children'),
     Output('missed-trips-05', 'children'),
     Output('missed-trips-11', 'children'),
     Output('current-time', 'children'),],
    Input('interval-component', 'n_intervals')
)
def update_dual_simulation(n):
    results = []
    for selected_date_str in ["2022-05-05", "2022-05-11"]:
        global stations_global, last_update_time_global

        # Prevent duplicate interval processing
        if selected_date_str not in last_frame_global:
            last_frame_global[selected_date_str] = -1

        if n <= last_frame_global[selected_date_str]:
            raise dash.exceptions.PreventUpdate

        last_frame_global[selected_date_str] = n

        trip_df = trip_dfs[selected_date_str]
        sim_date = datetime.strptime(selected_date_str, "%Y-%m-%d")
        current_sim_time = sim_date + timedelta(seconds=n * SPEED_MULTIPLIER)
        progress_percent = int(min((n / 300) * 100, 100))
        
        # Create pending return list if it's the first time
        if selected_date_str not in in_transit_bikes_global:
            in_transit_bikes_global[selected_date_str] = []

        pending_returns = in_transit_bikes_global[selected_date_str]

        # Stations start with 5 bikes and the simulation starts from midnight of the chosen day
        if (
            selected_date_str not in stations_global or
            selected_date_str not in in_transit_bikes_global or
            selected_date_str not in last_update_time_global
        ):
            sim_date = datetime.strptime(selected_date_str, "%Y-%m-%d")
            in_transit_bikes_global[selected_date_str] = []
            last_update_time_global[selected_date_str] = sim_date

            if selected_date_str == "2022-05-05":
                with open("datasets/missed_trips.csv", "w") as f:
                    f.write("")

            # Reset bikes and timer
            stations_global[selected_date_str] = {
                str(sid): {
                    "bike_count": 30,
                    "missed_trips": 0,
                    "completed_trips": 0,
                    "was_empty": 0,
                    "was_full": 0,
                    "activity_count": 0,
                    "status": None
                }for sid in station_df['station_id']}
            last_update_time_global[selected_date_str] = sim_date

        bike_counts = stations_global[selected_date_str]
        last_time = last_update_time_global[selected_date_str]
        
        # Return bikes whose end_time has arrived
        to_return = [trip for trip in pending_returns if trip['end_time'] <= current_sim_time]
        for trip in to_return:
            end_id = trip['end_id']
            if end_id in stations_global[selected_date_str]:
                stations_global[selected_date_str][end_id]["bike_count"] += 1
            else:
                print(f"⚠️ Warning: End station {end_id} not found in stations_global for {selected_date_str}")
            pending_returns.remove(trip)
        
        # Track how often each station is empty or full
        for sid in stations_global[selected_date_str]:
            bike_count = stations_global[selected_date_str][sid]["bike_count"]
            if bike_count == 0:
                stations_global[selected_date_str][sid]["was_empty"] += 1
            elif bike_count >= 10:
                stations_global[selected_date_str][sid]["was_full"] += 1


        new_trips = trip_df[
            (trip_df['start_time'] >= last_time) &
            (trip_df['start_time'] < current_sim_time)
        ]
        
        missed_trip_rows = []

        for _, trip in new_trips.iterrows():
            start_id = str(trip['start_station_id'])
            end_id = str(trip['end_station_id'])
            end_time = trip['end_time']

            if start_id in stations_global[selected_date_str]:
                if stations_global[selected_date_str][start_id]["bike_count"] > 0:
                    stations_global[selected_date_str][start_id]["bike_count"] -= 1
                    in_transit_bikes_global[selected_date_str].append({
                        "end_time": end_time,
                        "end_id": end_id
                    })
                    stations_global[selected_date_str][start_id]["completed_trips"] += 1
                    stations_global[selected_date_str][start_id]["activity_count"] += 1

                else:
                    missed_trip_rows.append({
                        "trip_id": trip['trip_id'],
                        "start_time": trip['start_time'],
                        "end_time": end_time,
                        "start_station_id": start_id,
                        "end_station_id": end_id,
                        "simulated_day": selected_date_str
                    })
                    stations_global[selected_date_str][start_id]["missed_trips"] += 1
                    stations_global[selected_date_str][start_id]["activity_count"] += 1
            else:
                print(f"⚠️ Skipped trip: Start station {start_id} not found in stations_global for {selected_date_str}")

        if missed_trip_rows:
            new_df = pd.DataFrame(missed_trip_rows)

            if not new_df.empty:
                append_df_with_header_check(new_df, "datasets/missed_trips.csv")

        last_update_time_global[selected_date_str] = current_sim_time
        
        # Export stats once simulation reaches 100%
        if progress_percent == 100:
            # Evaluate and assign status
            for sid, data in stations_global[selected_date_str].items():
                total_frames = 300  # or use n if dynamic
                empty_ratio = data["was_empty"] / total_frames
                full_ratio = data["was_full"] / total_frames
                total_activity = data["activity_count"]

                if total_activity > BUSY_THRESHOLD:
                    status = "busy"
                elif total_activity < UNDERUSED_THRESHOLD:
                    status = "underused"
                elif empty_ratio > 0.25:
                    status = "always_empty"
                elif full_ratio > 0.25:
                    status = "always_full"
                else:
                    status = "balanced"

                data["status"] = status
                
            # Prepare CSV export    
            stats_rows = []
            for sid, data in stations_global[selected_date_str].items():
                stats_rows.append({
                    "station_id": sid,
                    "completed_trips": data["completed_trips"],
                    "missed_trips": data["missed_trips"],
                    "final_bike_count": data["bike_count"],
                    "simulated_day": selected_date_str,
                    "status": data["status"]
                })

            pd.DataFrame(stats_rows).to_csv(f"datasets/station_stats_{selected_date_str}.csv", index=False)
        
            
        # === Create the map figure ===
        latitudes = []
        longitudes = []
        colors = []
        sizes = []
        hover_texts = []

        for _, row in station_df.iterrows():
            sid = str(row['station_id'])
            lat = row['lat']
            lon = row['lon']
            name = row['station_name']
            count = stations_global[selected_date_str][sid]["bike_count"]
            color = get_color(count)

            latitudes.append(lat)
            longitudes.append(lon)
            colors.append(color)
            sizes.append(min(5 + 0.5 * count, 15))
            # Only show status in tooltip if simulation is complete
            if progress_percent == 100:
                status_line = f"<br>Status: {stations_global[selected_date_str][sid]['status']}"
            else:
                status_line = ""

            hover_texts.append(f"{name}<br><br>Bikes: {count}{status_line}")


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
            showlegend=False
        )
        results.extend([fig, f"❌ Missed trips: {len(missed_trip_rows)}"])

    # Progress bar
    timer_text = f"Progress: {progress_percent}%"

    return (results[0], results[2], progress_percent, timer_text, results[1], results[3], f"Time:  {current_sim_time.strftime('%H:%M')}")

# === Run the app ===
if __name__ == '__main__':
    app.run(debug=True)