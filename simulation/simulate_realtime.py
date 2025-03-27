# simulation/simulate_realtime.py

import pandas as pd
from datetime import datetime, timedelta
import time

def run_realtime_simulation(trip_df, duration_minutes=20):
    sim_start = datetime(2022, 5, 5, 0, 0)
    sim_end = datetime(2022, 5, 5, 23, 59)

    real_duration_seconds = duration_minutes * 60
    sim_total_seconds = (sim_end - sim_start).total_seconds()
    speed_multiplier = sim_total_seconds / real_duration_seconds

    print(f"Each real second = {speed_multiplier:.2f} seconds of simulation time.")

    real_start_time = time.time()
    current_sim_time = sim_start

    while current_sim_time < sim_end:
        elapsed_real_seconds = time.time() - real_start_time
        current_sim_time = sim_start + timedelta(seconds=elapsed_real_seconds * speed_multiplier)

        # Filter trips happening now
        active_trips = trip_df[
            (trip_df['start_time'] <= current_sim_time) &
            (trip_df['end_time'] > current_sim_time)
        ]

        # Count bikes at each station
        bikes_per_station = active_trips['start_station_id'].value_counts().to_dict()

        yield current_sim_time, bikes_per_station

        time.sleep(1)  # Wait 1 real second before next step
