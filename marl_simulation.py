import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from marl_demand_utils import load_historical_demand
from marl_demand_utils import choose_action 
from plotly.graph_objects import Figure 

import os
import csv

missed_path = "datasets/missed_trips_marl.csv"
# Write header only once, if file does not exist
if not os.path.exists(missed_path):
    with open(missed_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["trip_id", "start_time", "end_time", "start_station_id", "end_station_id", "simulated_day"])

station_df = pd.read_csv("datasets/all_stations.csv")
trip_dfs = {
    "2022-05-05": pd.read_csv("datasets/all_trips_05_05.csv", parse_dates=["start_time", "end_time"]),
    "2022-05-11": pd.read_csv("datasets/all_trips_05_11.csv", parse_dates=["start_time", "end_time"]),
}
initial_bike_counts = {}
stats_df = pd.read_csv("datasets/station_stats_2022-05-05.csv")

redistribution_mapping = {
    row["station_id"]: row["status"]
    for _, row in stats_df.iterrows()
}

for _, row in stats_df.iterrows():
    sid = str(row["station_id"])
    initial_bike_counts[sid] = row["final_bike_count"]

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
early_redistribution_done = set()
redistribution_in_transit_list = {}


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
    
def perform_early_morning_redistribution(
    stations,
    redistribution_in_transit_list,
    selected_date,
    current_time,
    target_level = 18
):
    """
    Move bikes from stations with surplus (> target_level)
    to stations with deficit (< target_level), and record
    those moves so that they show up as halos in the map.
    """
    # 1) Identify donors and receivers
    donors = {sid: data for sid, data in stations.items()
              if data["bike_count"] > target_level}
    receivers = {sid: data for sid, data in stations.items()
                 if data["bike_count"] < target_level}

    for sid_from, data_from in donors.items():
        surplus = data_from["bike_count"] - target_level
        if surplus <= 0:
            continue

        for sid_to, data_to in receivers.items():
            deficit = target_level - data_to["bike_count"]
            if deficit <= 0:
                continue

            move_qty = min(surplus, deficit)

            # Update counts
            stations[sid_from]["bike_count"] -= move_qty
            stations[sid_to]["bike_count"]   += move_qty
            stations[sid_from]["early_sent_glow"] = 3 
            
            redistribution_in_transit_list.append({
                "end_id": sid_to,
                "quantity": move_qty,
                "end_time": current_time + timedelta(minutes=45),
                "from_id": sid_from  
            })

            print(f"  🚚 {move_qty} bikes moved from {sid_from} → {sid_to}")

            surplus -= move_qty
            if surplus <= 0:
                break   


# Main function of MARL sim
def run_marl_simulation_step(n, stations_marl_global, in_transit_marl_global, last_update_marl_global, last_frame_marl_frame, redistribution_in_transit_list):
    results = []
    missed_path = f"datasets/missed_trips_marl.csv"

    for selected_date in ["2022-05-05", "2022-05-11"]:
        trip_df = trip_dfs[selected_date]
        sim_date = datetime.strptime(selected_date, "%Y-%m-%d")
        current_time = sim_date + timedelta(seconds=n * SPEED_MULTIPLIER)

         # Create redistribution list if not exists
        if "redistribution_in_transit_list" not in in_transit_marl_global:
            in_transit_marl_global["redistribution_in_transit_list"] = {}

        if selected_date not in in_transit_marl_global["redistribution_in_transit_list"]:
            in_transit_marl_global["redistribution_in_transit_list"][selected_date] = []

        redistribution_in_transit_list = in_transit_marl_global["redistribution_in_transit_list"][selected_date]

        # Init state
        if n == 0 or selected_date not in stations_marl_global:
            stations_marl_global[selected_date] = {
                sid: {
                    "bike_count": initial_bike_counts.get(sid, 30),
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
            redistribution_in_transit_list = in_transit_marl_global["redistribution_in_transit_list"][selected_date]
            
            # ✅ Overwrite missed_trips_marl.csv for fresh start (only once)
            if selected_date == "2022-05-05":
                with open("datasets/missed_trips_marl.csv", "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["trip_id", "start_time", "end_time", "start_station_id", "end_station_id", "simulated_day"])

        stations = stations_marl_global[selected_date]
        in_transit = in_transit_marl_global[selected_date]
        last_time = last_update_marl_global[selected_date]
        
        # Skip duplicate frames
        if selected_date not in last_frame_marl_frame:
            last_frame_marl_frame[selected_date] = -1
        if n <= last_frame_marl_frame[selected_date]:
            from dash.exceptions import PreventUpdate
            raise PreventUpdate
        
        last_frame_marl_frame[selected_date] = n
        
        # Early redistribution trigger (3:00–4:00)
        if selected_date not in early_redistribution_done:
            if 3 <= current_time.hour < 4:
                perform_early_morning_redistribution(
                    stations,
                    redistribution_in_transit_list,
                    selected_date,
                    current_time,
                    target_level=18
                )
                early_redistribution_done.add(selected_date)

        # Handle returns
        to_return = [trip for trip in in_transit if trip["end_time"] <= current_time]
        for trip in to_return:
            end_id = str(trip["end_id"])
            if end_id in stations:
                stations[end_id]["bike_count"] += 1
            in_transit.remove(trip)
            
        # Handle redistributed bikes arriving after delay
        redistributed_arrivals = [t for t in redistribution_in_transit_list if t["end_time"] <= current_time]
        for trip in redistributed_arrivals:
            if trip["end_id"] in stations:
                stations[trip["end_id"]]["bike_count"] += trip["quantity"]
                stations[trip["end_id"]]["received_bikes"] += trip["quantity"]
                stations[trip["end_id"]]["early_received_glow"] = 3  

            redistribution_in_transit_list.remove(trip)

            
        # Track how often each MARL station is empty or full
        for sid in stations:
            count = stations[sid]["bike_count"]
            if count == 0:
                stations[sid]["was_empty"] += 1
            elif count >= 27:
                stations[sid]["was_full"] += 1


        for sid in stations:
            stations[sid]["just_missed"] = False
    
        # Handle new trips
        new_trips = trip_df[
            (trip_df["start_time"] >= last_time) & (trip_df["start_time"] < current_time)
        ]
        missed = 0
        stations[sid]["just_missed"] = False


        for _, row in new_trips.iterrows():
            start_id = str(row["start_station_id"])
            end_id = str(row["end_station_id"])
            trip_time = row["start_time"]

            # Only process trips that should happen right now (current_time window)
            if trip_time <= current_time:
                if start_id in stations and stations[start_id]["bike_count"] > 0:
                    stations[start_id]["bike_count"] -= 1
                    in_transit.append({
                        "end_time": row["end_time"],
                        "end_id": end_id
                    })
                    stations[start_id]["completed_trips"] += 1
                else:
                    stations[start_id]["missed_trips"] += 1
                    missed += 1
                    stations[start_id]["just_missed"] = True


                    # Save missed trip to CSV
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
        
        # === Step 2: Choose and execute actions ONLY during 12:00–12:59 for both days ===
        if 12 <= current_hour < 13:
            for sid, obs in agent_observations.items():
                neighbors = [nid for nid in stations if nid != sid]

                # Unpack action tuple from agent
                action_type, target_station, quantity = choose_action(sid, obs, neighbors)

                # Save the last action
                stations[sid]["previous_action"] = (action_type, target_station, quantity)

                if action_type == "do_nothing":
                    continue

                elif action_type == "send_bikes":
                    if stations[sid]["bike_count"] >= quantity:
                        stations[sid]["bike_count"] -= quantity
                        stations[sid]["sent_bikes"] += quantity

                        if target_station in stations:
                            redistribution_in_transit_list.append({
                                "end_time": current_time + timedelta(minutes=45),
                                "end_id": target_station,
                                "quantity": quantity
                            })

                elif action_type == "request_bikes":
                    if target_station in stations and stations[target_station]["bike_count"] >= quantity:
                        stations[target_station]["bike_count"] -= quantity
                        stations[target_station]["sent_bikes"] += quantity

                        redistribution_in_transit_list.append({
                            "end_time": current_time + timedelta(minutes=45),
                            "end_id": sid,
                            "quantity": quantity
                        })

                    
        # Off-peak redistribution (only on May 11)
        
        # === Draw map ===
        lats, lons, colors, sizes, hovers = [], [], [], [], []
        # === Step 1: Track which stations sent or received redistributed bikes recently ===
        show_redistribution_icons = []
        redistribution_color_map = []

        for sid in stations:
            station = stations[sid]
            sent = station.get("sent_bikes", 0)
            received = station.get("received_bikes", 0)

            # If redistribution just occurred within the last hour
            if 12 <= current_time.hour <= 13:
                if received > 0:
                    show_redistribution_icons.append((sid, "received"))
                elif sent > 0:
                    show_redistribution_icons.append((sid, "sent"))


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
            hovers.append(f"{name}<br><br>Bikes: {count}<br>Sent / Received: {sent} / {received}")

        fig = draw_map(stations, station_df, current_time)

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

            stats_rows = []
            for sid, data in stations.items():
                # Get total outgoing/incoming from historical demand (May 5th)
                # Store into results[2] and results[5]
                # Compute dynamically for both days
                total_out = sum(historical_demand[selected_date]["outgoing"][sid].values())
                total_in = sum(historical_demand[selected_date]["incoming"][sid].values())

                # Assign summary to correct side
                if selected_date == "2022-05-05":
                    results[2] = summary_text
                else:
                    results[5] = summary_text

                    
                # Determine status
                activity = data["completed_trips"] + data["missed_trips"]
                empty_ratio = data["was_empty"] / 300
                full_ratio = data["was_full"] / 300

                if activity > 188:
                    status = "busy"
                elif activity < 58:
                    status = "underused"
                elif empty_ratio > 0.25:
                    status = "always_empty"
                elif full_ratio > 0.25:
                    status = "always_full"
                else:
                    status = "balanced"

                # Healthy %
                healthy_frames = 300 - data["was_empty"] - data["was_full"]
                healthy_percentage = round((healthy_frames / 300) * 100)

                stats_rows.append({
                    "station_id": sid,
                    "completed_trips": data["completed_trips"],
                    "missed_trips": data["missed_trips"],
                    "final_bike_count": data["bike_count"],
                    "simulated_day": selected_date,
                    "status": status,
                    "total_outgoing": total_out,
                    "total_incoming": total_in,
                    "healthy_percentage": healthy_percentage
                })

            filename = f"datasets/station_stats_marl_{selected_date}.csv"
            pd.DataFrame(stats_rows).to_csv(filename, index=False)
            print(f"✅ MARL stats exported to {filename}")

        for station in stations.values():
            if isinstance(station.get("early_sent_glow"), int) and station["early_sent_glow"] > 0:
                station["early_sent_glow"] -= 1
            if isinstance(station.get("early_received_glow"), int) and station["early_received_glow"] > 0:
                station["early_received_glow"] -= 1

        last_update_marl_global[selected_date] = current_time

    return (
        results[0],  # map_marl_05_05
        results[3],  # map_marl_05_11
        results[1],  # missed-trips-marl-05
        results[4],  # missed-trips-marl-11
        results[2],  # summary-marl-left
        results[5],  # summary-marl-right
    )

def draw_map(stations, station_df, current_time):
    import plotly.graph_objects as go

    fig = go.Figure()
    lats, lons, colors, sizes, hovers = [], [], [], [], []

    # Base station markers and hovers
    for _, row in station_df.iterrows():
        sid = str(row["station_id"])
        lat, lon = row["lat"], row["lon"]
        name = row["station_name"]
        count = stations.get(sid, {}).get("bike_count", 0)
        sent = stations.get(sid, {}).get("sent_bikes", 0)
        received = stations.get(sid, {}).get("received_bikes", 0)

        lats.append(lat)
        lons.append(lon)
        colors.append(get_color(count))
        sizes.append(min(9 + 0.5 * count, 15))
        hovers.append(f"{name}<br><br>Bikes: {count}<br>Sent / Received: {sent} / {received}")

    # --- Glow logic ---
    for sid in stations:
        station = stations[sid]
        row = station_df[station_df["station_id"] == sid]
        if row.empty:
            continue
        lat = row.iloc[0]["lat"]
        lon = row.iloc[0]["lon"]

        # 💙 Early morning sender glow
        if isinstance(station.get("early_sent_glow"), int) and station["early_sent_glow"] > 0:
            fig.add_trace(go.Scattermapbox(
                lat=[lat],
                lon=[lon],
                mode="markers",
                marker=go.scattermapbox.Marker(size=22, color="cyan", opacity=0.8),
                hoverinfo="skip",
                showlegend=False
            ))

        # 💚 Early morning receiver glow
        if isinstance(station.get("early_received_glow"), int) and station["early_received_glow"] > 0:
            fig.add_trace(go.Scattermapbox(
                lat=[lat],
                lon=[lon],
                mode="markers",
                marker=go.scattermapbox.Marker(size=22, color="chartreuse", opacity=0.8),
                hoverinfo="skip",
                showlegend=False
            ))

    # 💫 MARL redistribution halos (12:00–13:00)
    if 12 <= current_time.hour <= 13:
        for sid in stations:
            station = stations[sid]
            row = station_df[station_df["station_id"] == sid]
            if row.empty:
                continue
            lat = row.iloc[0]["lat"]
            lon = row.iloc[0]["lon"]

            if station.get("sent_bikes", 0) > 0:
                fig.add_trace(go.Scattermapbox(
                    lat=[lat],
                    lon=[lon],
                    mode="markers",
                    marker=go.scattermapbox.Marker(size=22, color="cyan", opacity=0.8),
                    hoverinfo="skip",
                    showlegend=False
                ))
            elif station.get("received_bikes", 0) > 0:
                fig.add_trace(go.Scattermapbox(
                    lat=[lat],
                    lon=[lon],
                    mode="markers",
                    marker=go.scattermapbox.Marker(size=22, color="chartreuse", opacity=0.8),
                    hoverinfo="skip",
                    showlegend=False
                ))

    # ⛔ Missed trip glow
    for sid in stations:
        station = stations[sid]
        if station.get("just_missed", False):
            row = station_df[station_df["station_id"] == sid]
            if row.empty:
                continue
            lat = row.iloc[0]["lat"]
            lon = row.iloc[0]["lon"]
            size = min(9 + 0.5 * station["bike_count"], 15) + 5

            fig.add_trace(go.Scattermapbox(
                lat=[lat],
                lon=[lon],
                mode="markers",
                marker=go.scattermapbox.Marker(size=size, color="black", opacity=1),
                hoverinfo="skip",
                showlegend=False
            ))

    # Add final visible markers (stations)
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

    return fig
