import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Load data
station_df = pd.read_csv("datasets/all_stations.csv")
trip_dfs = {
    "2022-05-05": pd.read_csv("datasets/all_trips_05_05.csv", parse_dates=["start_time", "end_time"]),
    "2022-05-11": pd.read_csv("datasets/all_trips_05_11.csv", parse_dates=["start_time", "end_time"]),
}

SPEED_MULTIPLIER = (24 * 60 * 60) / (5 * 60)  # 24h in 5min

# Helper function for marker colors
def get_color(count):
    if count == 0: return "red"
    elif count <= 15: return "orange"
    elif 15 < count <= 30: return "green"
    else: return "blue"

# Main function to run 1 step of MARL sim
def run_marl_simulation_step(n, stations_marl_global, in_transit_marl_global, last_update_marl_global, last_frame_marl_frame):
    results = []
    
    for selected_date in ["2022-05-05", "2022-05-11"]:
        trip_df = trip_dfs[selected_date]
        sim_date = datetime.strptime(selected_date, "%Y-%m-%d")
        current_time = sim_date + timedelta(seconds=n * SPEED_MULTIPLIER)

        # Skip duplicate frames
        if selected_date not in last_frame_marl_frame:
            last_frame_marl_frame[selected_date] = -1
        if n <= last_frame_marl_frame[selected_date]:
            from dash.exceptions import PreventUpdate
            raise PreventUpdate
        last_frame_marl_frame[selected_date] = n

        # Init state
        if n == 0 or selected_date not in stations_marl_global:
            stations_marl_global[selected_date] = {
                sid: {"bike_count": 30} for sid in station_df["station_id"].astype(str)
            }
            in_transit_marl_global[selected_date] = []
            last_update_marl_global[selected_date] = sim_date

        stations = stations_marl_global[selected_date]
        in_transit = in_transit_marl_global[selected_date]
        last_time = last_update_marl_global[selected_date]

        # Handle returns
        to_return = [trip for trip in in_transit if trip["end_time"] <= current_time]
        for trip in to_return:
            end_id = str(trip["end_id"])
            if end_id in stations:
                stations[end_id]["bike_count"] += 1
            in_transit.remove(trip)

        # Handle new trips
        new_trips = trip_df[
            (trip_df["start_time"] >= last_time) & (trip_df["start_time"] < current_time)
        ]
        missed = 0

        for _, row in new_trips.iterrows():
            start_id = str(row["start_station_id"])
            end_id = str(row["end_station_id"])
            if start_id in stations and stations[start_id]["bike_count"] > 0:
                stations[start_id]["bike_count"] -= 1
                in_transit.append({
                    "end_time": row["end_time"],
                    "end_id": end_id
                })
            else:
                missed += 1

        # === Draw map ===
        lats, lons, colors, sizes, hovers = [], [], [], [], []

        for _, row in station_df.iterrows():
            sid = str(row["station_id"])
            lat, lon = row["lat"], row["lon"]
            name = row["station_name"]
            count = stations.get(sid, {}).get("bike_count", 0)

            lats.append(lat)
            lons.append(lon)
            colors.append(get_color(count))
            sizes.append(min(5 + 0.5 * count, 15))
            hovers.append(f"{name}<br>Bikes: {count}")

        fig = go.Figure()
        fig.add_trace(go.Scattermapbox(
            lat=lats, lon=lons,
            mode="markers",
            marker=go.scattermapbox.Marker(size=sizes, color=colors, opacity=0.8),
            text=hovers,
            hoverinfo='text'
        ))
        fig.update_layout(
            mapbox=dict(
                style="carto-positron",
                center=dict(lat=sum(lats)/len(lats), lon=sum(lons)/len(lons)),
                zoom=12
            ),
            margin=dict(l=0, r=0, t=30, b=0),
            showlegend=False
        )

        results.extend([
            fig,
            f"❌ Missed Trips: {missed}",
            ""
        ])

        last_update_marl_global[selected_date] = current_time

    return (
        results[0],  # map_marl_05_05
        results[3],  # map_marl_05_11
        results[1],  # missed-trips-marl-05
        results[4],  # missed-trips-marl-11
        results[2],  # summary-marl-left
        results[5],  # summary-marl-right
    )
