import plotly.express as px
import pandas as pd

def show_madrid_map():
    # Load your stations data
    df = pd.read_csv('datasets/all_stations.csv')

    fig = px.scatter_map(
        df,
        lat="lat",
        lon="lon",
        hover_name="unlock_station_name",   # Show station name when hovering
        zoom=12,
        height=900,
        title="Bike Stations in Madrid"
    )

    fig.update_layout(
        mapbox_style="open-street-map",
        mapbox_center={"lat": 60.3913, "lon": 5.3221},
        margin={"r": 0, "t": 40, "l": 0, "b": 0}
    )

    fig.show()

if __name__ == "__main__":
    show_madrid_map()
