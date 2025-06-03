import dash
from dash.dependencies import Input, Output
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from layout import layout
from marl_simulation import run_marl_simulation_step
import warnings
import os

# To ignore the warning about the Scattermap
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Append a DataFrame to a CSV, and include the header if the file is missing or empty.
def append_df_with_header_check(df, path):
    write_header = not os.path.exists(path) or os.stat(path).st_size == 0
    df.to_csv(path, mode='a', header=write_header, index=False)

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

station_stats = {
    "2022-05-05": pd.read_csv("datasets/station_stats_2022-05-05.csv"),
    "2022-05-11": pd.read_csv("datasets/station_stats_2022-05-11.csv")
}

# === Dash App ===
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
app.title = "Madrid Bike-Sharing Map Simulation"
app.layout = layout

if not os.path.exists("missed_trips.csv"):
    pd.DataFrame(columns=[
        "trip_id", "start_time", "end_time", "start_station_id", "end_station_id", "simulated_day"
    ]).to_csv("datasets/missed_trips.csv", index=False)

# === Global simulation state ===
stations_global = {} #  dict of current bikes per station {station_id: bike_count}
in_transit_bikes_global = {} # bikes currently being used, scheduled to return at end_time
last_update_time_global = {} # last simulation time processed per date
last_frame_global = {} # last Dash frame (n) processed per date

stations_marl_global = {}
in_transit_marl_global = {}
last_update_marl_global = {}
last_frame_marl_frame = {}
redistribution_in_transit = {}
STATION_CAPACITY = 30

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
     Output('current-time', 'children'),
     Output('summary-left', 'children'),
     Output('summary-right', 'children'),],
    Input('interval-component', 'n_intervals')
)
def update_dual_simulation(n):
    summary_left_text = ""
    summary_right_text = ""
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
                    "final_missed_trips": 0,
                    "completed_trips": 0,
                    "was_empty": 0,
                    "was_full": 0,
                    "activity_count": 0,
                    "status": None,
                    "has_missed": False,
                    "just_missed": False,
                    "healthy_time": 0,
                    "availability_sum": 0
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
            elif bike_count >= 27:
                stations_global[selected_date_str][sid]["was_full"] += 1

            #  Count healthy frames 
            if 16 <= bike_count <= 30:
                stations_global[selected_date_str][sid]["healthy_time"] += 1
                
            # Track availability % over time
            if "availability_sum" not in stations_global[selected_date_str][sid]:
                stations_global[selected_date_str][sid]["availability_sum"] = 0
            stations_global[selected_date_str][sid]["availability_sum"] +=  bike_count / STATION_CAPACITY * 100


        new_trips = trip_df[
            (trip_df['start_time'] >= last_time) &
            (trip_df['start_time'] < current_sim_time)
        ]
        
        missed_trip_rows = []
        for sid in stations_global[selected_date_str]:
            stations_global[selected_date_str][sid]["just_missed"] = False


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
                    stations_global[selected_date_str][start_id]["final_missed_trips"] += 1
                    stations_global[selected_date_str][start_id]["has_missed"] = True
                    stations_global[selected_date_str][start_id]["just_missed"] = True  
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
            
            total_completed = sum(data["completed_trips"] for data in stations_global[selected_date_str].values())
            total_missed = sum(data["final_missed_trips"] for data in stations_global[selected_date_str].values())
            total_bikes = sum(data["bike_count"] for data in stations_global[selected_date_str].values())
            
            if (total_completed + total_missed) > 0:
                trip_completion_rate = round((total_completed / (total_completed + total_missed)) * 100, 2)
            else:
                trip_completion_rate = 0
                
            station_availabilities = [
                data["availability_sum"] / 300  # 300 frames in a day
                for data in stations_global[selected_date_str].values()
                if "availability_sum" in data
            ]
            overall_availability = round(sum(station_availabilities) / len(station_availabilities), 2)

            summary_text = f"""✅ Completed: {total_completed} | ❌ Missed: {total_missed} | 🚲 Remaining Bikes: {total_bikes} | 🎯 Completion Rate: {trip_completion_rate}% | 📈 Availability: {overall_availability}% """

            # === Save to daily_summary.csv ===
            summary_row = {
                "simulated_day": selected_date_str,
                "method": "basic",
                "completed_trips": total_completed,
                "missed_trips": total_missed,
                "completion_rate": trip_completion_rate,
                "rebalancing_cost": 0,
                "avg_availability": overall_availability
            }

            summary_path = "datasets/daily_summary.csv"
            write_header = not os.path.exists(summary_path) or os.stat(summary_path).st_size == 0
            pd.DataFrame([summary_row]).to_csv(summary_path, mode="a", header=write_header, index=False)
            
            if selected_date_str == "2022-05-05":
                summary_left_text = summary_text
            else:
                summary_right_text = summary_text
                
            
            # Prepare CSV export    
            stats_rows = []
            for sid, data in stations_global[selected_date_str].items():
                # Get total outgoing/incoming from precomputed stats
                stat_row = station_stats[selected_date_str]
                stat_row = stat_row[stat_row["station_id"] == sid]
                if not stat_row.empty:
                    outgoing = int(stat_row["total_outgoing"].values[0])
                    incoming = int(stat_row["total_incoming"].values[0])
                else:
                    outgoing = 0
                    incoming = 0
                
                healthy_frames = data.get("healthy_time", 0)
                healthy_percentage = round(healthy_frames / total_frames * 100)

                stats_rows.append({
                    "station_id": sid,
                    "completed_trips": data["completed_trips"],
                    "final_missed_trips": data["final_missed_trips"],
                    "final_bike_count": data["bike_count"],
                    "simulated_day": selected_date_str,
                    "status": data["status"],
                    "total_outgoing": outgoing,
                    "total_incoming": incoming,
                    "healthy_percentage": healthy_percentage
                })
            pd.DataFrame(stats_rows).to_csv(f"datasets/station_stats_{selected_date_str}.csv", index=False)
            
        # === Create the map figure ===
        latitudes = []
        longitudes = []
        colors = []
        sizes = []
        hover_texts = []
        missed_flags = [stations_global[selected_date_str][str(row["station_id"])]["just_missed"] for _, row in station_df.iterrows()]

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
            sizes.append(min(9 + 0.5 * count, 15))
            # Only show status in tooltip if simulation is complete
            status = stations_global[selected_date_str][sid]["status"]
    
            if progress_percent == 100:
                status = stations_global[selected_date_str][sid]["status"]
                
                # Lookup trip info for this station
                stats_row = station_stats[selected_date_str]
                stats_row = stats_row[stats_row["station_id"] == sid]
                if not stats_row.empty:
                    outgoing = int(stats_row["total_outgoing"].values[0])
                    incoming = int(stats_row["total_incoming"].values[0])
                    trips_line = f"<br>Total Outgoing / Incoming: {outgoing} / {incoming}"
                else:
                    trips_line = ""

                status_line = f"<br>Status: {status}"
                missed_line = f"<br>Missed Trips: {stations_global[selected_date_str][sid]['final_missed_trips']}"
                healthy_frames = stations_global[selected_date_str][sid].get("healthy_time", 0)
                healthy_percentage = round(healthy_frames / total_frames * 100)
                healthy_line = f"<br>Healthy Time: {healthy_percentage}%"
                avg_availability = round(stations_global[selected_date_str][sid]["availability_sum"] / total_frames, 2)
                availability_rate = f"<br><b>Avg Availability: {avg_availability}%"
            else:
                status_line = ""
                trips_line = ""
                missed_line = ""
                healthy_line = ""
                availability = round(100 * count / STATION_CAPACITY, 2)
                availability_rate = f"<br>Availability: {availability}%"

            hover_texts.append(f"{name}<br><br>Bikes: {count}{status_line}{trips_line}{missed_line}{healthy_line}{availability_rate}")

        fig = go.Figure()

        # Black halo trace (for missed trips)
        fig.add_trace(go.Scattermapbox(
            lat=[latitudes[i] for i in range(len(latitudes)) if missed_flags[i]],
            lon=[longitudes[i] for i in range(len(longitudes)) if missed_flags[i]],
            mode="markers",
            marker=go.scattermapbox.Marker(
                size=[sizes[i] + 5 for i in range(len(sizes)) if missed_flags[i]],
                color="black",
                opacity=1,
            ),
            hoverinfo='skip',
            showlegend=False
        ))

        # Actual station trace
        fig.add_trace(go.Scattermapbox(
            lat=latitudes,
            lon=longitudes,
            mode="markers",
            marker=go.scattermapbox.Marker(
                size=sizes,
                color=colors,
                opacity=0.9
            ),
            text=hover_texts,
            hoverinfo='text',
            name="Stations"
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

    return (results[0], results[2], progress_percent, timer_text, results[1], results[3], f"Time:  {current_sim_time.strftime('%H:%M')}", summary_left_text, summary_right_text )

@app.callback(
    [Output('map_marl_05_05', 'figure'),
     Output('map_marl_05_11', 'figure'),
     Output('missed-trips-marl-05', 'children'),
     Output('missed-trips-marl-11', 'children'),
     Output('summary-marl-left', 'children'),
     Output('summary-marl-right', 'children')],
    Input('interval-component', 'n_intervals')
)
def update_marl_simulation(n):
    return run_marl_simulation_step(n, stations_marl_global, in_transit_marl_global, last_update_marl_global, last_frame_marl_frame, redistribution_in_transit)

# === Run the app ===
if __name__ == '__main__':
    app.run(debug=True)