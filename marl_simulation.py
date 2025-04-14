import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from marl_demand_utils import load_historical_demand
from marl_demand_utils import choose_action  

import os
import csv

# Ensure missed trips file exists with headers
missed_path = "datasets/missed_trips_marl.csv"
if not os.path.exists(missed_path):
    with open(missed_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "trip_id", "start_time", "end_time",
            "start_station_id", "end_station_id", "simulated_day"
        ])


station_df = pd.read_csv("datasets/all_stations.csv")
trip_dfs = {
    "2022-05-05": pd.read_csv("datasets/all_trips_05_05.csv", parse_dates=["start_time", "end_time"]),
    "2022-05-11": pd.read_csv("datasets/all_trips_05_11.csv", parse_dates=["start_time", "end_time"]),
}
# Dictionary to hold outgoing/incoming data per day
historical_demand = {}

# Loop over all available trip DataFrames (e.g., for May 5 and May 11)
for day, df in trip_dfs.items():
    outflow, inflow = load_historical_demand(df)
    historical_demand[day] = {
        "outgoing": outflow,
        "incoming": inflow
    }

SPEED_MULTIPLIER = (24 * 60 * 60) / (5 * 60)  # 24h in 5min

# Helper function for marker colors
def get_color(count):
    if count == 0: return "red"
    elif count <= 15: return "orange"
    elif 15 < count <= 30: return "green"
    else: return "blue"

def build_agent_observation(station_id, current_hour, station_data, historical_demand, selected_date, total_frames):
    # Builds the full observation dictionary for a station-agent.
    station_data = station_data.get(station_id, {})

    outgoing = historical_demand[selected_date]["outgoing"][station_id].get(current_hour, 0)
    incoming = historical_demand[selected_date]["incoming"][station_id].get(current_hour, 0)

    was_empty_ratio = station_data.get("was_empty", 0) / total_frames if total_frames > 0 else 0
    was_full_ratio = station_data.get("was_full", 0) / total_frames if total_frames > 0 else 0

    return {
        "current_bike_count": station_data.get("bike_count", 0),
        "historical_demand_next_hr": outgoing,
        "historical_inflow_next_hr": incoming,
        "was_empty_ratio": was_empty_ratio,
        "was_full_ratio": was_full_ratio,
        "current_hour": current_hour,
        "previous_action": station_data.get("previous_action", "do_nothing")
    }

# Main function of MARL sim
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
                sid: {
                    "bike_count": 30,
                    "completed_trips": 0,
                    "missed_trips": 0,
                    "was_empty": 0,
                    "was_full": 0,
                    "previous_action": "do_nothing",
                    "sent_bikes": 0,
                    "received_bikes": 0
                }for sid in station_df["station_id"].astype(str)
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
            
        # Track how often each MARL station is empty or full
        for sid in stations:
            count = stations[sid]["bike_count"]
            if count == 0:
                stations[sid]["was_empty"] += 1
            elif count >= 27:
                stations[sid]["was_full"] += 1


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
                stations[start_id]["completed_trips"] += 1
            else:
                # Missed trip handling
                stations[start_id]["missed_trips"] += 1
                missed += 1

                # Save this missed trip to CSV
                with open(missed_path, "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        row["trip_id"],
                        row["start_time"],
                        row["end_time"],
                        start_id,
                        end_id,
                        selected_date
                    ])
                
        # Build Observation for each agent
        total_frames = n + 1
        current_hour = current_time.hour

        agent_observations = {
            sid: build_agent_observation(
                sid, current_hour,
                stations, historical_demand,
                selected_date, total_frames
            )
            for sid in stations
        }
        
        for sid, obs in agent_observations.items():
            neighbors = [nid for nid in stations if nid != sid]

            # Unpack tuple-based action
            action_type, target_station, quantity = choose_action(sid, obs, neighbors)

            # Save the last action
            stations[sid]["previous_action"] = (action_type, target_station, quantity)

            if action_type == "do_nothing":
                continue

            elif action_type == "send_bikes":
                if stations[sid]["bike_count"] >= quantity:
                    stations[sid]["bike_count"] -= quantity

                    if target_station in stations:
                        stations[target_station]["bike_count"] += quantity
                        stations[sid]["sent_bikes"] += quantity
                        stations[target_station]["received_bikes"] += quantity

            elif action_type == "request_bikes":
                if target_station in stations and stations[target_station]["bike_count"] >= quantity:
                    stations[target_station]["bike_count"] -= quantity
                    stations[sid]["bike_count"] += quantity
                    stations[sid]["received_bikes"] += quantity
                    stations[target_station]["sent_bikes"] += quantity

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
            sizes.append(min(9 + 0.5 * count, 15))
            sent = stations.get(sid, {}).get("sent_bikes", 0)
            received = stations.get(sid, {}).get("received_bikes", 0)
            hovers.append(f"{name}<br>Bikes: {count}<br>Sent: {sent}<br>Received: {received}")


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
        
        if n == 300:  # Only print when simulation ends
            print(f"\n Simulation Summary for {selected_date}:")

            # === 1. Empty / Full Count Debug ===
            print("\n Empty / Full Tracking (first 5 stations):")
            for sid, data in list(stations.items())[:5]:
                print(f"  Station {sid} → was_empty: {data['was_empty']}, was_full: {data['was_full']}")

            # === 2. Incoming / Outgoing Demand Debug ===
            current_hour = current_time.hour
            print(f"\n Historical Demand (Hour {current_hour}) for first 5 stations:")
            for sid in list(stations.keys())[:5]:
                outgoing = historical_demand[selected_date]["outgoing"][sid].get(current_hour, 0)
                incoming = historical_demand[selected_date]["incoming"][sid].get(current_hour, 0)
                print(f"  Station {sid} → Outgoing: {outgoing}, Incoming: {incoming}")
                
            print(f"\n🧠 Agent Observations for {selected_date} (first 5 stations):")
            for sid, obs in list(agent_observations.items())[:5]:
                print(f"  {sid}: {obs}")
                
            print(f"\n🔄 Bike Movements for {selected_date} (first 5 stations):")
            for sid, data in list(stations.items())[:5]:
                print(f"  {sid}: Sent → {data['sent_bikes']} | Received → {data['received_bikes']}")

            # Summary text for Dash
            total_completed = sum(data["completed_trips"] for data in stations.values())
            total_missed = sum(data["missed_trips"] for data in stations.values())
            total_bikes = sum(data["bike_count"] for data in stations.values())

            summary_text = f"""✅ Total completed trips: {total_completed} | ❌ Total missed trips: {total_missed} | 🚲 Total bikes remaining: {total_bikes}"""

            # Store into results[2] and results[5]
            if selected_date == "2022-05-05":
                results[2] = summary_text
            else:
                results[5] = summary_text



        last_update_marl_global[selected_date] = current_time

    return (
        results[0],  # map_marl_05_05
        results[3],  # map_marl_05_11
        results[1],  # missed-trips-marl-05
        results[4],  # missed-trips-marl-11
        results[2],  # summary-marl-left
        results[5],  # summary-marl-right
    )
