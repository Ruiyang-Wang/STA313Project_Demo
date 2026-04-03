"""
STA313 Project - Interactive Mapping of Public & Private Retreats for Students
Group 10 | Streamlit Application
"""

import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import json
import os

# ============================================================
# Config
# ============================================================
st.set_page_config(page_title="Third Places for Students in Toronto", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")

# University coordinates and colors
UNIVERSITIES = {
    "University of Toronto": {"lat": 43.6629, "lon": -79.3957, "color": "#002A5C"},
    "TMU": {"lat": 43.6577, "lon": -79.3788, "color": "#FFC72A"},
    "OCAD": {"lat": 43.6512, "lon": -79.3922, "color": "#E31837"},
}

ZONE_COLORS = {
    "University of Toronto": "#002A5C",
    "TMU": "#FFC72A",
    "OCAD": "#E31837",
    "Other": "#D3D3D3",
}

PLACE_COLORS = {
    "park": "#2ca02c",
    "cafe": "#ff7f0e",
    "library": "#1f77b4",
}


# ============================================================
# Data Loading (cached)
# ============================================================
@st.cache_data
def load_places():
    return pd.read_csv(os.path.join(PROCESSED_DIR, "all_places.csv"))


@st.cache_data
def load_crime():
    return pd.read_csv(os.path.join(PROCESSED_DIR, "crime_aggregated.csv"))


@st.cache_data
def load_neighbourhoods():
    gdf = gpd.read_file(os.path.join(PROCESSED_DIR, "neighbourhoods_with_zones.geojson"))
    return gdf


@st.cache_data
def get_neighbourhood_zone_map():
    """Map HOOD_158 code to university_zone."""
    gdf = load_neighbourhoods()
    return dict(zip(gdf["AREA_SHORT_CODE"].astype(str), gdf["university_zone"]))


# ============================================================
# Sidebar Controls
# ============================================================
st.sidebar.title("Filters")

# Layer toggles
st.sidebar.subheader("Place Types")
show_parks = st.sidebar.checkbox("Parks", value=True)
show_cafes = st.sidebar.checkbox("Cafes", value=True)
show_libraries = st.sidebar.checkbox("Libraries", value=True)

# WiFi filter
st.sidebar.subheader("Amenities")
wifi_only = st.sidebar.checkbox("Only show places near free WiFi")

# Cost filter
cost_filter = st.sidebar.radio("Cost", ["All", "Free Only", "Paid Only"])

# Campus selection
st.sidebar.subheader("Campus Focus")
campus_options = ["All Toronto"] + list(UNIVERSITIES.keys())
selected_campus = st.sidebar.selectbox("Select Campus", campus_options)

# Crime year range
st.sidebar.subheader("Crime Data")
crime_df = load_crime()
min_year = int(crime_df["OCC_YEAR"].min())
max_year = int(crime_df["OCC_YEAR"].max())
year_range = st.sidebar.slider("Year Range", min_year, max_year, (max_year - 2, max_year))


# ============================================================
# Filter Places
# ============================================================
places = load_places()

# Place type filter
selected_types = []
if show_parks:
    selected_types.append("park")
if show_cafes:
    selected_types.append("cafe")
if show_libraries:
    selected_types.append("library")

filtered = places[places["place_type"].isin(selected_types)]

# WiFi filter
if wifi_only:
    filtered = filtered[filtered["nearby_wifi"] == True]

# Cost filter
if cost_filter == "Free Only":
    filtered = filtered[filtered["cost"] == "free"]
elif cost_filter == "Paid Only":
    filtered = filtered[filtered["cost"] == "paid"]

# Campus filter - assign zone to each place based on nearest neighbourhood
if selected_campus != "All Toronto":
    uni = UNIVERSITIES[selected_campus]
    # Filter to places within ~3km of the selected campus
    from math import radians, cos, sin, sqrt, atan2

    def haversine(lat1, lon1, lat2, lon2):
        R = 6371000  # meters
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        return R * 2 * atan2(sqrt(a), sqrt(1 - a))

    filtered = filtered[
        filtered.apply(
            lambda row: haversine(row["lat"], row["lon"], uni["lat"], uni["lon"]) <= 3000,
            axis=1,
        )
    ]


# ============================================================
# Main Title
# ============================================================
st.title("Third Places for Students in Toronto")
st.caption("Interactive map of parks, cafes, and libraries for university students")
st.markdown("*A STA313 Group Project Demo*")

# Stats row
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Places", len(filtered))
col2.metric("Parks", len(filtered[filtered["place_type"] == "park"]))
col3.metric("Cafes", len(filtered[filtered["place_type"] == "cafe"]))
col4.metric("Libraries", len(filtered[filtered["place_type"] == "library"]))


# ============================================================
# Build Map
# ============================================================
if selected_campus != "All Toronto":
    uni = UNIVERSITIES[selected_campus]
    map_center = [uni["lat"], uni["lon"]]
    map_zoom = 14
else:
    map_center = [43.7, -79.4]
    map_zoom = 11

m = folium.Map(location=map_center, zoom_start=map_zoom, tiles="CartoDB positron")

# Add neighbourhood polygons with university zone coloring
neighbourhoods = load_neighbourhoods()
folium.GeoJson(
    neighbourhoods,
    style_function=lambda feature: {
        "fillColor": ZONE_COLORS.get(feature["properties"].get("university_zone", "Other"), "#D3D3D3"),
        "color": "#666666",
        "weight": 0.5,
        "fillOpacity": 0.15,
    },
    tooltip=folium.GeoJsonTooltip(
        fields=["AREA_NAME", "university_zone"],
        aliases=["Neighbourhood:", "University Zone:"],
        style="font-size: 12px;",
    ),
).add_to(m)

# Add university markers
for uni_name, uni_info in UNIVERSITIES.items():
    folium.Marker(
        location=[uni_info["lat"], uni_info["lon"]],
        popup=uni_name,
        icon=folium.Icon(color="red", icon="university", prefix="fa"),
    ).add_to(m)

# Add place markers as GeoJSON for performance
for place_type in selected_types:
    type_data = filtered[filtered["place_type"] == place_type]
    if len(type_data) == 0:
        continue

    color = PLACE_COLORS[place_type]

    features = []
    for _, row in type_data.iterrows():
        wifi_status = "Yes" if row.get("nearby_wifi", False) else "No"
        name = str(row.get("name", "N/A")).replace('"', "'")
        addr = str(row.get("address", "N/A")).replace('"', "'")
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            "properties": {
                "name": name,
                "type": place_type.title(),
                "cost": str(row.get("cost", "N/A")).title(),
                "wifi": wifi_status,
                "address": addr,
            },
        })

    geojson_data = {"type": "FeatureCollection", "features": features}

    folium.GeoJson(
        geojson_data,
        name=place_type.title(),
        marker=folium.CircleMarker(radius=4, fill=True, fill_opacity=0.7, weight=1),
        style_function=lambda feature, c=color: {
            "color": c,
            "fillColor": c,
            "radius": 4,
            "weight": 1,
            "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["name", "type", "cost", "wifi", "address"],
            aliases=["Name:", "Type:", "Cost:", "WiFi Nearby:", "Address:"],
            style="font-size: 11px;",
        ),
    ).add_to(m)

# Render map
st_folium(m, width=None, height=600, returned_objects=[])


# ============================================================
# Legend
# ============================================================
st.markdown("""
<div style="display: flex; gap: 20px; margin: 10px 0;">
    <span><span style="color: #2ca02c; font-size: 18px;">&#9679;</span> Parks</span>
    <span><span style="color: #ff7f0e; font-size: 18px;">&#9679;</span> Cafes</span>
    <span><span style="color: #1f77b4; font-size: 18px;">&#9679;</span> Libraries</span>
    <span><span style="color: red; font-size: 14px;">&#9873;</span> University</span>
</div>
""", unsafe_allow_html=True)


# ============================================================
# Crime Bar Chart
# ============================================================
st.subheader("Crime Statistics")

# Filter crime data by year range
crime_filtered = crime_df[
    (crime_df["OCC_YEAR"] >= year_range[0]) & (crime_df["OCC_YEAR"] <= year_range[1])
]

# Filter by campus zone if selected
if selected_campus != "All Toronto":
    zone_map = get_neighbourhood_zone_map()
    crime_filtered = crime_filtered[
        crime_filtered["HOOD_158"].astype(str).map(zone_map) == selected_campus
    ]

# Aggregate by MCI_CATEGORY
crime_agg = (
    crime_filtered.groupby("MCI_CATEGORY")["count"]
    .sum()
    .reset_index()
    .sort_values("count", ascending=False)
)

if len(crime_agg) > 0:
    # Title
    area_label = selected_campus if selected_campus != "All Toronto" else "Toronto"
    chart_title = f"Crime Incidents in {area_label} ({year_range[0]}-{year_range[1]})"

    fig = px.bar(
        crime_agg,
        x="MCI_CATEGORY",
        y="count",
        color="MCI_CATEGORY",
        title=chart_title,
        labels={"MCI_CATEGORY": "Crime Category", "count": "Incident Count"},
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(showlegend=False, xaxis_tickangle=-30, height=400)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No crime data available for the selected filters.")


# ============================================================
# Footer
# ============================================================
st.markdown("---")
st.caption(
    "Data sources: City of Toronto Open Data Portal | Toronto Police Service Public Safety Data Portal"
)
