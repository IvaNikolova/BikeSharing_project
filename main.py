import plotly.express as px
import pandas as pd

def show_toronto_map():
    # Create a dummy DataFrame just to initialize the map
    df = pd.DataFrame({
        'lat': [60.3913],
        'lon': [5.3221]
    })

    fig = px.scatter_map(
        df,
        lat="lat",
        lon="lon",
        zoom=11,
        height=900,
        title="Bergen City Map"
    )

    fig.update_layout(
        mapbox_style="open-street-map",  # Open source style, no token needed
        margin={"r": 0, "t": 40, "l": 0, "b": 0}
    )

    # Hide the dummy point
    fig.data[0].marker.opacity = 0

    fig.show()

if __name__ == "__main__":
    show_toronto_map()
