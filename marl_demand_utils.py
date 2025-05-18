import pandas as pd
from collections import defaultdict

def load_historical_demand(trip_df):
    # Create nested dictionaries with default value of 0
    # Structure: outgoing["station_id"]["hour"] = count
    outgoing = defaultdict(lambda: defaultdict(int))
    incoming = defaultdict(lambda: defaultdict(int))

    for _, row in trip_df.iterrows():
        start_id = str(row['start_station_id'])
        end_id = str(row['end_station_id'])

        start_hour = row['start_time'].hour
        end_hour = row['end_time'].hour

        outgoing[start_id][start_hour] += 1
        incoming[end_id][end_hour] += 1

    return outgoing, incoming
