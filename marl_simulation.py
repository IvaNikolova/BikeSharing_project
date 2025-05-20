import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from marl_demand_utils import load_historical_demand
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
station_demand = {str(row["station_id"]): row["completed_trips"] for _, row in stats_df.iterrows()}
sorted_demand = sorted(station_demand.items(), key=lambda x: x[1], reverse=True)
demand_receivers = [sid for sid, _ in sorted_demand[:60]]  # Top 60 stations
demand_donors = [sid for sid, _ in sorted_demand[-60:]]    # Bottom 60 stations
rebalancing_cost_global = {
        "2022-05-05": 0,
        "2022-05-11": 0
    }

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
STATION_CAPACITY = 30

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
    target_level = 18,
    rebalancing_cost=0,
    rebalancing_cost_global=None):
   
    # Identify donors and receivers
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
            rebalancing_cost += move_qty
            rebalancing_cost_global[selected_date] += move_qty  
            print(f"🧾 Early-morning: +{move_qty} → rebalancing_cost for {selected_date} = {rebalancing_cost_global[selected_date]}")
            
            redistribution_in_transit_list.append({
                "end_id": sid_to,
                "quantity": move_qty,
                "end_time": current_time + timedelta(minutes=45),
                "from_id": sid_from  
            })

            # print(f"  🚚 {move_qty} bikes moved from {sid_from} → {sid_to}")
            surplus -= move_qty
            if surplus <= 0:
                break  
            
    return rebalancing_cost
 

# Main function of MARL sim
def run_marl_simulation_step(n, stations_marl_global, in_transit_marl_global, last_update_marl_global, last_frame_marl_frame, redistribution_in_transit_list):
    results = []
    missed_path = f"datasets/missed_trips_marl.csv"
    
    blank_fig = go.Figure()
    blank_fig.update_layout(
        mapbox_style="carto-positron",
        mapbox_zoom=12,
        mapbox_center={"lat": 40.4168, "lon": -3.7038}
    )
    results = [blank_fig, "", "", blank_fig, "", ""]  # pre-fill map placeholders

    for selected_date in ["2022-05-05", "2022-05-11"]:
        trip_df = trip_dfs[selected_date]
        sim_date = datetime.strptime(selected_date, "%Y-%m-%d")
        current_time = sim_date + timedelta(seconds=n * SPEED_MULTIPLIER)
        rebalancing_cost = 0

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
            
            # Overwrite missed_trips_marl.csv for fresh start (only once)
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
                rebalancing_cost = perform_early_morning_redistribution(
                    stations,
                    redistribution_in_transit_list,
                    selected_date,
                    current_time,
                    target_level=18,
                    rebalancing_cost=rebalancing_cost,
                    rebalancing_cost_global=rebalancing_cost_global                )
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

            # Track availability % over time
            availability = 100 * count / STATION_CAPACITY
            if "availability_sum" not in stations[sid]:
                stations[sid]["availability_sum"] = 0
            stations[sid]["availability_sum"] += availability


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
        
        # Demand-based redistribution (12:00–13:00) 
        if 12 <= current_hour < 13:
            for sid_from in demand_donors:
                if sid_from not in stations or stations[sid_from]["bike_count"] <= 18:
                    continue

                for sid_to in demand_receivers:
                    if sid_to not in stations:
                        continue

                    if stations[sid_to]["bike_count"] >= 30:
                        continue

                    move_qty = min(stations[sid_from]["bike_count"] - 18, 30 - stations[sid_to]["bike_count"])
                    if move_qty <= 0:
                        continue

                    stations[sid_from]["bike_count"] -= move_qty
                    stations[sid_to]["received_bikes"] += move_qty
                    stations[sid_from]["sent_bikes"] += move_qty  
                    rebalancing_cost += move_qty
                    rebalancing_cost_global[selected_date] += move_qty
                    redistribution_in_transit_list.append({
                        "end_time": current_time + timedelta(minutes=45),
                        "end_id": sid_to,
                        "quantity": move_qty
                    })
                    print(f"🧾 Noon: +{move_qty} → rebalancing_cost for {selected_date} = {rebalancing_cost_global[selected_date]}")
        
        # === Draw map ===
        lats, lons, colors, sizes, hovers = [], [], [], [], []
        # === Track which stations sent or received redistributed bikes recently ===
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
        if selected_date == "2022-05-05":
            results[0] = fig  # map
            results[1] = f"❌ Missed Trips: {missed}"
        elif selected_date == "2022-05-11":
            results[3] = fig  # map
            results[4] = f"❌ Missed Trips: {missed}"

        
        if n == 300:  # Only print when simulation ends
            # Make sure results has at least 6 slots (for index 2 and 5)
            while len(results) < 6:
                results.append("")
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
                #print(f"  Station {sid} → Outgoing: {outgoing}, Incoming: {incoming}")
                
            # print(f"\n🧠 Agent Observations for {selected_date} (first 5 stations):")
            #for sid, obs in list(agent_observations.items())[:5]:
            #    print(f"  {sid}: {obs}")
                
            # print(f"\n🔄 Bike Movements for {selected_date} (first 5 stations):")
            #for sid, data in list(stations.items())[:5]:
            #    print(f"  {sid}: Sent → {data['sent_bikes']} | Received → {data['received_bikes']}")

            # Summary text for Dash
           
            stats_rows = []
            
            total_completed = sum(data["completed_trips"] for data in stations.values())
            total_missed = sum(data["missed_trips"] for data in stations.values())
            total_bikes = sum(data["bike_count"] for data in stations.values())
            
            if (total_completed + total_missed) > 0:
                trip_completion_rate = round((total_completed / (total_completed + total_missed)) * 100, 2)
            else:
                trip_completion_rate = 0

            station_availabilities = [
                data["availability_sum"] / 300  # 300 frames in a day
                for data in stations.values()
                if "availability_sum" in data
            ]
            overall_availability = round(sum(station_availabilities) / len(station_availabilities), 2)

            cost = rebalancing_cost_global[selected_date]      
            summary_text = f"""✅ Completed: {total_completed} | ❌ Missed: {total_missed} | 🚲 Remaining Bikes: {total_bikes} | 🎯 Completion Rate: {trip_completion_rate}% | 📈 Availability: {overall_availability}% | 💸 Rebalancing Cost: {cost}"""

            print(f"✅ FINAL rebalancing cost for {selected_date}: {cost}")
            print(f"📊 Summary Text for {selected_date}: {summary_text}")

            # === Save to daily_summary.csv ===
            summary_row = {
                "simulated_day": selected_date,
                "method": "MARL",
                "completed_trips": total_completed,
                "missed_trips": total_missed,
                "completion_rate": trip_completion_rate,
                "rebalancing_cost": cost,
                "avg_availability": overall_availability
            }

            summary_path = "datasets/daily_summary_marl.csv"
            write_header = not os.path.exists(summary_path) or os.stat(summary_path).st_size == 0
            pd.DataFrame([summary_row]).to_csv(summary_path, mode="a", header=write_header, index=False)

            # Assign summary to correct side
            if selected_date == "2022-05-05":
                results[2] = summary_text
            else:
                results[5] = summary_text
            
            for sid, data in stations.items():
                # Get total outgoing/incoming from historical demand (May 5th)
                # Store into results[2] and results[5]
                # Compute dynamically for both days
                total_out = sum(historical_demand[selected_date]["outgoing"][sid].values())
                total_in = sum(historical_demand[selected_date]["incoming"][sid].values())

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
                    "healthy_percentage": healthy_percentage,
                    "avg_availability": round(data.get("availability_sum", 0) / 300, 2)
                })

            filename = f"datasets/station_stats_marl_{selected_date}.csv"
            pd.DataFrame(stats_rows).to_csv(filename, index=False)
            #print(f"✅ MARL stats exported to {filename}")

        for station in stations.values():
            if isinstance(station.get("early_sent_glow"), int) and station["early_sent_glow"] > 0:
                station["early_sent_glow"] -= 1
            if isinstance(station.get("early_received_glow"), int) and station["early_received_glow"] > 0:
                station["early_received_glow"] -= 1
                
            if 12 <= current_time.hour < 13:
                continue  # keep glow active
            station["sent_bikes"] = 0
            station["received_bikes"] = 0

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
        if current_time.hour == 00 and current_time.minute == 00:
            availability = round(stations[sid].get("availability_sum", 0) / 300, 2)
            hovers.append(f"{name}<br><br>Bikes: {count}<br><b>Avg Availability: {availability}%</b>")
        else:
            availability = round(100 * count / STATION_CAPACITY, 2)
            hovers.append(f"{name}<br><br>Bikes: {count}<br>Availability: {availability}%")

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
