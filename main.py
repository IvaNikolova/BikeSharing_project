import pandas as pd
import plotly.express as px
from simulation.simulate_realtime import run_realtime_simulation

def show_station_map(station_df, bikes_per_station):
    df = station_df.copy()
    df['bike_count'] = df['station_id'].map(bikes_per_station).fillna(0)

    fig = px.scatter_map(
        df,
        lat="lat",
        lon="lon",
        size="bike_count",       # 🔁 This changes based on simulation
        color="bike_count",
        hover_name="station_name",
        size_max=15,
        zoom=12,
        height=900,
        title="Live Bike Count in Madrid"
    )
    fig.update_layout(
        mapbox_style="open-street-map",
        mapbox_center={"lat": 40.4168, "lon": -3.7038},
        margin={"r": 0, "t": 40, "l": 0, "b": 0}
    )
    fig.show()

if __name__ == "__main__":
    trip_df = pd.read_csv("datasets/all_trips.csv", parse_dates=["start_time", "end_time"])
    station_df = pd.read_csv("datasets/all_stations.csv")

    for sim_time, bikes_per_station in run_realtime_simulation(trip_df, duration_minutes=20):
        print(f"🕐 {sim_time.strftime('%H:%M')} | Updating map...")
        show_station_map(station_df, bikes_per_station)
