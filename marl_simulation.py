import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from marl_demand_utils import load_historical_demand
from plotly.graph_objects import Figure 
import os
import csv
from dqn_agent import DQNAgent, StationAgent

missed_path = "datasets/missed_trips_marl.csv"
CKPT_PATH = "./checkpoints/dqn_agent.pth"

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

# —— DQN imports & initialization ——
# Define your state/action dimensions (must match StationAgent._obs_to_vector)
state_dim  = 8   # [count, demand_out, demand_in, empty_ratio, full_ratio, hour, prev_action]
action_dim = 7   # 1 “do nothing” + 3 “send X” + 3 “request X” (we’ll map these below)

# Shared DQN agent and one StationAgent per station
shared_agent  = DQNAgent(state_dim=state_dim, action_dim=action_dim)
#shared_agent.load(CKPT_PATH)
station_ids   = station_df["station_id"].astype(str).tolist()
station_agents = {
    sid: StationAgent(station_id=sid, agent=shared_agent)
    for sid in station_ids
}
# — end DQN setup —

initial_bike_counts = {}
stats_df = pd.read_csv("datasets/station_stats_2022-05-05.csv")
station_demand = {str(row["station_id"]): row["completed_trips"] for _, row in stats_df.iterrows()}

rebalancing_cost_global = {
        "2022-05-05": 0,
        "2022-05-11": 0
    }

moved_3_4_global   = { date: 0 for date in rebalancing_cost_global }
moved_12_13_global = { date: 0 for date in rebalancing_cost_global }

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
redistribution_in_transit_list = {}
STATION_CAPACITY = 40
STATIC_MAX_CAPACITY = STATION_CAPACITY + 20

# how many simulation‐steps make up a full day
STEPS_PER_DAY = 300

# these are your module‐level globals:
stations_marl_global       = {}
in_transit_marl_global     = {}
last_update_marl_global    = {}
last_frame_marl_frame      = {}
redistribution_in_transit  = []

def _reset_globals():
    """Clear out everything so we can start a fresh day."""
    stations_marl_global.clear()
    in_transit_marl_global.clear()
    last_update_marl_global.clear()
    last_frame_marl_frame.clear()
    # if you used per-date lists inside a dict, clear those too:
    redistribution_in_transit.clear()

# Helper function for marker colors
def get_color(count):
    if count == 0: return "red"
    elif count <= 15: return "orange"
    elif 15 < count <= 30: return "green"
    else: return "blue"

def build_agent_observation(
    station_id,
    current_hour,
    station_data,
    historical_demand,
    selected_date,
    total_frames,
    donors=None,
    receivers=None
):
    # Base two lines unchanged
    station_data = station_data.get(station_id, {})
    
    outgoing = historical_demand[selected_date]["outgoing"][station_id].get(current_hour, 0)
    incoming = historical_demand[selected_date]["incoming"][station_id].get(current_hour, 0)
    
    outgoing_1 = outgoing
    outgoing_2 = historical_demand[selected_date]["outgoing"][station_id].get(current_hour + 1, 0)
    outgoing_3 = historical_demand[selected_date]["outgoing"][station_id].get(current_hour + 2, 0)
    outgoing_4 = historical_demand[selected_date]["outgoing"][station_id].get(current_hour + 3, 0)
    outgoing_5 = historical_demand[selected_date]["outgoing"][station_id].get(current_hour + 4, 0)
    outgoing_5hr = outgoing_1 + outgoing_2 + outgoing_3 + outgoing_4 + outgoing_5


    was_empty_ratio = station_data.get("was_empty", 0) / total_frames if total_frames > 0 else 0
    was_full_ratio  = station_data.get("was_full",  0) / total_frames if total_frames > 0 else 0
    
    if donors is None or receivers is None:
        donors    = [station_id]
        receivers = [station_id]
    
    obs = {
        "current_bike_count":       station_data.get("bike_count", 0),
        "historical_demand_next_hr": outgoing,
        "historical_inflow_next_hr": incoming,
        "outgoing_5hr":              outgoing_5hr,
        "was_empty_ratio":           was_empty_ratio,
        "was_full_ratio":            was_full_ratio,
        "current_hour":              current_hour,
        "previous_action":           station_data.get("previous_action", "do_nothing"),
    }

    # ——— Wire in dynamic donors/receivers passed from run_marl_simulation_step ———
    if station_id in donors:
        partners = receivers[:3]
    else:
        partners = donors[:3]

    # Now actually put them into the observation
    for idx, pid in enumerate(partners, start=1):
        obs[f"top_partner_{idx}"] = pid
    # If fewer than 3 partners, fill the rest with “do_nothing”
    for idx in range(len(partners)+1, 4):
        obs[f"top_partner_{idx}"] = station_id  # self-loop => “do nothing”


    return obs

    
def compute_reward_for_station(station_id, stations, missed_weight=50.0, move_weight=0.005):
    """
    Composite reward:
      -10 × missed_trips
      + 2 × completed_trips
      - 0.1 × bikes_moved
      - 0.2 × deviation from ideal_level (set later)
    """
    s = stations[station_id]
    # 1) Missed/completed
    r = - missed_weight * s.get("missed_trips", 0)
    # 2) Cost of moves
    moved = s.get("sent_bikes", 0) + s.get("received_bikes", 0)
    r   -= move_weight * moved
    # 3) Deviation from dynamic ideal—filled in by caller
    # 4) Overflow penalty
    overflow = s.get("overflow_attempts", 0)
    r        -= 5.0 * overflow
    
    return r
    
def transfer_bikes(from_id: str, to_id: str, qty: int, stations: dict):
    """
    Immediately move `qty` bikes from station `from_id` to station `to_id`.
    Updates bike_count, plus sent_bikes / received_bikes counters.
    """
    # Safety clamp: don’t go negative
    moved = min(qty, stations[from_id]["bike_count"])
    
    # Decrement origin
    stations[from_id]["bike_count"] -= moved
    stations[from_id]["sent_bikes"]      = stations[from_id].get("sent_bikes", 0) + moved

    # Increment destination
    stations[to_id]["bike_count"]        = stations[to_id].get("bike_count", 0) + moved
    stations[to_id]["received_bikes"]    = stations[to_id].get("received_bikes", 0) + moved

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
        
        # ——— Dynamic per-station capacity ———
        station_capacity = {}
        for sid, data in stations.items():
            # sum outgoing demand for next 3 hours
            future_demand = sum(
                historical_demand[selected_date]["outgoing"][sid].get(h, 0)
                for h in range(current_hour, current_hour + 3)
            )
            # allow +1 slot per 5 forecasted trips, up to + 20 extra
            extra_slots = min(future_demand // 5, 20)
            station_capacity[sid] = STATION_CAPACITY + extra_slots
        # ————————————————————————————————

        # Handle returns
        to_return = [trip for trip in in_transit if trip["end_time"] <= current_time]
        for trip in to_return:
            end_id = str(trip["end_id"])
            if end_id in stations:
                # riders always return their bikes
                stations[end_id]["bike_count"] += 1
            in_transit.remove(trip)
            
        # Handle redistributed bikes arriving after delay
        redistributed_arrivals = [t for t in redistribution_in_transit_list if t["end_time"] <= current_time]
        for trip in redistributed_arrivals:
            end_id = str(trip["end_id"])
            if end_id in stations:
               # we planned correctly, so just add back every bike we moved
                # we guaranteed this at plan time—just add back everything
                stations[end_id]["bike_count"] += trip["quantity"]
                stations[end_id]["received_bikes"] += trip["quantity"]
                stations[end_id]["early_received_glow"] = 3

            redistribution_in_transit_list.remove(trip)
        
        # == 3:00–4:00 equal‐spread rebalancing ==
        if 3 <= current_hour < 4:
            counts = [data["bike_count"] for data in stations.values()]
            avg = sum(counts) // len(counts)
            donors    = {sid: data["bike_count"] - avg
                         for sid, data in stations.items() if data["bike_count"] > avg}
            receivers = {sid: avg - data["bike_count"]
                         for sid, data in stations.items() if data["bike_count"] < avg}
            for from_id, surplus in donors.items():
                for to_id, need in list(receivers.items()):
                    qty = min(surplus, need)
                    qty = min(qty, stations[from_id]["bike_count"])  # <-- clamp to what’s actually there
                    if qty <= 0:
                        continue
                    
                    # 1) schedule the move for +1 hour
                    redistribution_in_transit_list.append({
                        "from_id":    from_id,
                        "end_id":     to_id,
                        "quantity":   qty,
                        "end_time":   current_time + timedelta(hours=1)
                    })

                   # 2) immediately remove bikes from sender
                    stations[from_id]["bike_count"]   -= qty
                    stations[from_id]["sent_bikes"]   = stations[from_id].get("sent_bikes", 0) + qty

                    # 3) glow
                    stations[from_id]["early_sent_glow"] = 3

                    # 4) cost
                    rebalancing_cost += qty
                    rebalancing_cost_global[selected_date] += qty
                    moved_3_4_global[selected_date] += qty

                    # 5) reduce outstanding need
                    receivers[to_id] -= qty
                    surplus         -= qty

        
        # Demand-based redistribution (12:00–13:00) 
        if 12 <= current_hour < 13:
            # ——— DYNAMIC DONOR/RECEIVER RANKING ———
            # Score each station by (predicted demand next hour) - (current bike count)
            scores = {}
            for sid, data in stations.items():
                # data["historical_demand_next_hr"] is already in your obs,
                # but here we read directly from historical_demand
                demand = historical_demand[selected_date]["outgoing"][sid].get(current_hour, 0)
                bikes  = data["bike_count"]
                scores[sid] = demand - bikes

            # sort ascending: lowest scores (surplus) are donors, highest (need) are receivers
            sorted_sids = sorted(scores, key=scores.get)
            demand_donors    = sorted_sids[:60]
            demand_receivers = sorted_sids[-60:]
            # print(f"[12h] donors (first 5): {demand_donors[:5]}, receivers (first 5): {demand_receivers[:5]}")

            # ——————————————————————————————
            
            # 1) Build observations for every station
            observations = {
                sid: build_agent_observation(
                        station_id     = sid,
                        current_hour   = current_hour,
                        station_data   = stations,
                        historical_demand = historical_demand,
                        selected_date  = selected_date,
                        total_frames   = total_frames,
                        donors         = demand_donors,
                        receivers      = demand_receivers
                    )
                for sid in station_ids
            }

            # 2) Have each StationAgent choose an action
            actions = {
                sid: station_agents[sid].observe_and_act(observations[sid])
                for sid in station_ids
            }

            # 3) Map each action index to a concrete bike move
            moves = []      # list of (from_id, to_id, qty)
            for sid, act in actions.items():
                if act == 0:
                    continue  # do nothing
                # acts 1–3 = send 5 bikes to top_partner_1/2/3
                elif 1 <= act <= 3:
                    partner = observations[sid][f"top_partner_{act}"]
                    # only send as many as destination can hold
                    # how many we *could* add
                    desired = 5
                    free_slots = STATIC_MAX_CAPACITY - stations[partner]["bike_count"]
                    # record overflow attempts
                    overflow = max(0, desired - free_slots)
                    if overflow > 0:
                        stations[sid].setdefault("overflow_attempts", 0)
                        stations[sid]["overflow_attempts"] += overflow                    
                    send_qty  = min(5, stations[sid]["bike_count"], free_slots)
                    if send_qty > 0:
                        moves.append((sid, partner, send_qty))                
                # acts 4–6 = request 5 bikes from top_partner_{act-3}
                else:
                    partner = observations[sid][f"top_partner_{act-3}"]
                    moves.append((partner, sid, 5))

            # 4) Apply all moves in bulk
            for frm, to, requested_qty in moves:
                # clamp to what’s actually available
                moved_qty = min(requested_qty, stations[frm]["bike_count"])
                if moved_qty <= 0:
                  continue
        
                # remove from sender now
                stations[frm]["bike_count"] -= moved_qty
                stations[frm]["sent_bikes"] = stations[frm].get("sent_bikes", 0) + moved_qty
                stations[frm]["early_sent_glow"] = 1
        
                # schedule exactly what we removed
                redistribution_in_transit_list.append({
                    "from_id":  frm,
                    "end_id":   to,
                    "quantity": moved_qty,
                    "end_time": current_time + timedelta(hours=1)
                })
        
                # track the cost on the same moved_qty
                rebalancing_cost += moved_qty
                rebalancing_cost_global[selected_date] += moved_qty
                moved_12_13_global[selected_date] += moved_qty

        
            # 5) Record the reward & next observation for each station
            for sid in station_ids:
                # dynamic ideal: 1 slot per 2 forecasted trips + base 15
                outgoing = historical_demand[selected_date]["outgoing"][sid].get(current_hour, 0)
                ideal    = 15 + (outgoing / 2)
                # now get the reward
                reward = compute_reward_for_station(
                    sid, stations,
                    missed_weight=50.0,
                    move_weight=0.005
                )
                # subtract deviation from that ideal
                count = stations[sid]["bike_count"]
                reward -= 0.2 * abs(count - ideal)
                
                next_obs= build_agent_observation(
                             station_id = sid,
                             current_hour= current_hour,
                             station_data= stations,
                             historical_demand= historical_demand,
                             selected_date= selected_date,
                             total_frames= total_frames,
                             donors = demand_donors,
                             receivers = demand_receivers
                         )
                station_agents[sid].record(reward, next_obs, done=False)
            
            shared_agent.update()
            shared_agent.save(CKPT_PATH)
                
            #print("Replay buffer size:", len(shared_agent.replay_buffer))
            #print("Sample action dist:", {a: list(actions.values()).count(a) for a in set(actions.values())})

        
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
          #  print(f"\n Simulation Summary for {selected_date}:")

            # === 1. Empty / Full Count Debug ===
         #   print("\n Empty / Full Tracking (first 5 stations):")
          #  for sid, data in list(stations.items())[:5]:
         #      print(f"  Station {sid} → was_empty: {data['was_empty']}, was_full: {data['was_full']}")

            # === 2. Incoming / Outgoing Demand Debug ===
           # current_hour = current_time.hour
         #   print(f"\n Historical Demand (Hour {current_hour}) for first 5 stations:")
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
            # only count bikes actually at stations
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
            m3_4  = moved_3_4_global[selected_date]
            m12_13 = moved_12_13_global[selected_date]
      
            summary_text = f"""✅ Completed: {total_completed} | ❌ Missed: {total_missed} | 🚲 Remaining Bikes: {total_bikes} | 🎯 Completion Rate: {trip_completion_rate}% | 📈 Availability: {overall_availability}% | 💸 Rebalancing Cost: {cost} (🔄 Moved 3–4 h: {m3_4} & 🔄 Moved 12–13 h: {m12_13})"""

          #  print(f"✅ FINAL rebalancing cost for {selected_date}: {cost}")
           # print(f"📊 Summary Text for {selected_date}: {summary_text}")

            # === Save to daily_summary.csv ===
            summary_row = {
                "simulated_day": selected_date,
                "method": "MARL",
                "completed_trips": total_completed,
                "missed_trips": total_missed,
                "completion_rate": trip_completion_rate,
                "rebalancing_cost": cost,
                "avg_availability": overall_availability,
                "ramaining_bikes": total_bikes,
                "moved_3_4_h":   m3_4,
                "moved_12_13_h": m12_13,
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
            
            # ——— Train DQN with today’s experiences ———
            n_updates = 50
            for _ in range(n_updates):
                shared_agent.update()
                
           # print(f"End of day training done. ε = {shared_agent.epsilon:.3f}")

        for station in stations.values():
            if isinstance(station.get("early_sent_glow"), int) and station["early_sent_glow"] > 0:
                station["early_sent_glow"] -= 1
            if isinstance(station.get("early_received_glow"), int) and station["early_received_glow"] > 0:
                station["early_received_glow"] -= 1
                
           
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

def simulate_one_day():
    shared_agent.epsilon = max(shared_agent.epsilon, 0.2)

    """ Resets globals, runs a full day, trains, and returns (summary_text, cost). """
    # --- reset all per-day globals, leave shared_agent intact ---
    stations_marl_global.clear()
    in_transit_marl_global.clear()
    last_update_marl_global.clear()
    last_frame_marl_frame.clear()
    redistribution_in_transit.clear()

    for date in rebalancing_cost_global:
        rebalancing_cost_global[date] = 0
        moved_3_4_global[date]   = 0
        moved_12_13_global[date] = 0
        
    day_summary = None
    day_cost    = 0

    for n in range(STEPS_PER_DAY + 1):
        out = run_marl_simulation_step(
            n,
            stations_marl_global,
            in_transit_marl_global,
            last_update_marl_global,
            last_frame_marl_frame,
            redistribution_in_transit
        )
        if n == STEPS_PER_DAY:
            day_summary = out[4]

            # — Compute total_missed from final stations — 
            sim_date       = list(stations_marl_global.keys())[0]
            final_stations = stations_marl_global[sim_date]
            total_missed   = sum(s.get("missed_trips", 0) for s in final_stations.values())
            
            # global zero-miss bonus
            for sid, data in final_stations.items():   # ← use final_stations instead of stations
                if data.get("missed_trips", 0) == 0:
                    station_agents[sid].agent.store_transition(
                        station_agents[sid].last_state,
                        station_agents[sid].last_action,
                        20.0,                # per‐station zero‐miss bonus
                        station_agents[sid].last_state,
                        True
                    )
            # parse the cost directly from your global tracker, e.g.:
            day_cost = rebalancing_cost_global["2022-05-05"]

    return day_summary, day_cost