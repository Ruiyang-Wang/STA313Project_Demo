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
from shapely.geometry import Point
import os

# ============================================================
# Config
# ============================================================
st.set_page_config(page_title="Third Places for Students in Toronto", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")

UNIVERSITIES = {
    "University of Toronto": {"lat": 43.6629, "lon": -79.3957, "color": "#002A5C"},
    "TMU":                   {"lat": 43.6577, "lon": -79.3788, "color": "#FFC72A"},
    "OCAD":                  {"lat": 43.6512, "lon": -79.3922, "color": "#E31837"},
}

ZONE_COLORS = {
    "University of Toronto": "#002A5C",
    "TMU":                   "#FFC72A",
    "OCAD":                  "#E31837",
    "Other":                 "#AAAAAA",
}

PLACE_COLORS = {
    "park":    "#2ca02c",
    "cafe":    "#ff7f0e",
    "library": "#1f77b4",
}

CAFE_KEYWORDS = ["cafe", "tea", "coffee", "drink", "bakery", "bread", "dessert"]

CRIME_COLORS = {
    "Assault":        "#e45756",
    "Auto Theft":     "#72b7b2",
    "Break and Enter":"#f58518",
    "Robbery":        "#b279a2",
    "Theft Over":     "#54a24b",
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
    return gpd.read_file(os.path.join(PROCESSED_DIR, "neighbourhoods_with_zones.geojson"))


@st.cache_data
def get_neighbourhood_zone_map():
    """Map HOOD_158 (stripped) to university_zone."""
    gdf = load_neighbourhoods()
    # Normalize codes: strip leading zeros so "079" and "79" both become "79"
    codes = gdf["AREA_SHORT_CODE"].astype(str).apply(lambda x: str(int(x)) if x.isdigit() else x)
    return dict(zip(codes, gdf["university_zone"]))


@st.cache_data
def get_places_with_hood():
    """Spatial join places with neighbourhood polygons to get hood code and zone per place."""
    places = load_places()
    neighbourhoods = load_neighbourhoods()
    places_gdf = gpd.GeoDataFrame(
        places.copy(),
        geometry=gpd.points_from_xy(places["lon"], places["lat"]),
        crs="EPSG:4326",
    )
    hood_slim = neighbourhoods[["AREA_SHORT_CODE", "AREA_NAME", "university_zone", "geometry"]].copy()
    joined = gpd.sjoin(places_gdf, hood_slim, how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    places = places.copy()
    places["hood_code"]       = joined["AREA_SHORT_CODE"].astype(str).values
    places["university_zone"] = joined["university_zone"].fillna("Other").values
    return places


def normalize_hood(code):
    """Normalize neighbourhood code to stripped integer string, e.g. '079' -> '79'."""
    try:
        return str(int(str(code).strip()))
    except Exception:
        return str(code).strip()


# ============================================================
# Sidebar Controls
# ============================================================
st.sidebar.title("Filters")

# --- Place Types ---
st.sidebar.subheader("Place Types")
show_parks     = st.sidebar.checkbox("Parks",     value=True)
show_cafes     = st.sidebar.checkbox("Cafes",     value=True)
show_libraries = st.sidebar.checkbox("Libraries", value=True)

# --- Amenities ---
st.sidebar.subheader("Amenities")
wifi_only = st.sidebar.checkbox("Places Near Free Public Wifi")

# --- Cost ---
cost_filter = st.sidebar.radio("Cost", ["All", "Free Only", "Paid Only"])

# --- Campus Focus ---
st.sidebar.subheader("Campus Focus")
campus_options  = ["All Toronto", "All Campus"] + list(UNIVERSITIES.keys())
selected_campus = st.sidebar.selectbox("Select Campus", campus_options)

# University zone colour legend
st.sidebar.markdown(
    f"""
    <div style="font-size:13px; margin-top:4px; line-height:1.8;">
      <span style="background:{ZONE_COLORS['University of Toronto']};
                   color:white; padding:1px 6px; border-radius:3px;">UofT</span>
      &nbsp;University of Toronto<br>
      <span style="background:{ZONE_COLORS['TMU']};
                   color:#333; padding:1px 6px; border-radius:3px;">TMU</span>
      &nbsp;Toronto Metropolitan<br>
      <span style="background:{ZONE_COLORS['OCAD']};
                   color:white; padding:1px 6px; border-radius:3px;">OCAD</span>
      &nbsp;OCAD University<br>
      <span style="background:{ZONE_COLORS['Other']};
                   color:#333; padding:1px 6px; border-radius:3px;">—</span>
      &nbsp;Other
    </div>
    """,
    unsafe_allow_html=True,
)

# --- Crime Year Range ---
st.sidebar.subheader("Crime Data")
crime_df  = load_crime()
min_year  = int(crime_df["OCC_YEAR"].min())
max_year  = int(crime_df["OCC_YEAR"].max())
year_range = st.sidebar.slider("Year Range", min_year, max_year, (max_year - 2, max_year))


# ============================================================
# Filter Places
# ============================================================
places = load_places()

selected_types = []
if show_parks:     selected_types.append("park")
if show_cafes:     selected_types.append("cafe")
if show_libraries: selected_types.append("library")

filtered = places[places["place_type"].isin(selected_types)].copy()

# Improvement 1: Filter cafes by keyword in name
if show_cafes:
    cafe_mask = filtered["place_type"] != "cafe"  # keep non-cafes as-is
    keyword_pattern = "|".join(CAFE_KEYWORDS)
    keyword_mask = (
        filtered["place_type"].eq("cafe") &
        filtered["name"].astype(str).str.contains(keyword_pattern, case=False, na=False)
    )
    filtered = filtered[cafe_mask | keyword_mask]

# WiFi filter
if wifi_only:
    filtered = filtered[filtered["nearby_wifi"] == True]

# Cost filter
if cost_filter == "Free Only":
    filtered = filtered[filtered["cost"] == "free"]
elif cost_filter == "Paid Only":
    filtered = filtered[filtered["cost"] == "paid"]

# Campus filter — zone-based (uses spatial join result)
if selected_campus not in ("All Toronto",):
    places_zoned = get_places_with_hood()
    if selected_campus == "All Campus":
        keep_idx = places_zoned[places_zoned["university_zone"] != "Other"].index
    else:
        keep_idx = places_zoned[places_zoned["university_zone"] == selected_campus].index
    filtered = filtered[filtered.index.isin(keep_idx)]


# ============================================================
# Main Title
# ============================================================
st.title("Third Places for Students in Toronto")
st.caption("Interactive map of parks, cafes, and libraries for university students")

col1, col2, col3, col4 = st.columns(4)
col1.markdown(
    f'<p style="font-size:14px; margin-bottom:2px;">Total Places</p>'
    f'<p style="font-size:2rem; font-weight:700; margin:0;">{len(filtered)}</p>',
    unsafe_allow_html=True,
)
col2.markdown(
    f'<p style="font-size:14px; margin-bottom:2px;">'
    f'<span style="color:{PLACE_COLORS["park"]}; font-size:22px;">&#9679;</span> Parks</p>'
    f'<p style="font-size:2rem; font-weight:700; margin:0;">{len(filtered[filtered["place_type"]=="park"])}</p>',
    unsafe_allow_html=True,
)
col3.markdown(
    f'<p style="font-size:14px; margin-bottom:2px;">'
    f'<span style="color:{PLACE_COLORS["cafe"]}; font-size:22px;">&#9679;</span> Cafes</p>'
    f'<p style="font-size:2rem; font-weight:700; margin:0;">{len(filtered[filtered["place_type"]=="cafe"])}</p>',
    unsafe_allow_html=True,
)
col4.markdown(
    f'<p style="font-size:14px; margin-bottom:2px;">'
    f'<span style="color:{PLACE_COLORS["library"]}; font-size:22px;">&#9679;</span> Libraries</p>'
    f'<p style="font-size:2rem; font-weight:700; margin:0;">{len(filtered[filtered["place_type"]=="library"])}</p>',
    unsafe_allow_html=True,
)


# ============================================================
# Build Map
# ============================================================
if selected_campus in UNIVERSITIES:
    uni = UNIVERSITIES[selected_campus]
    map_center = [uni["lat"], uni["lon"]]
    map_zoom   = 14
else:
    map_center = [43.7, -79.4]
    map_zoom   = 11

m = folium.Map(location=map_center, zoom_start=map_zoom, tiles="CartoDB positron")

# Neighbourhood polygons
neighbourhoods = load_neighbourhoods()
folium.GeoJson(
    neighbourhoods,
    style_function=lambda feature: {
        "fillColor": ZONE_COLORS.get(
            feature["properties"].get("university_zone", "Other"), "#AAAAAA"
        ),
        "color":       "#666666",
        "weight":      0.5,
        "fillOpacity": 0.15,
    },
    tooltip=folium.GeoJsonTooltip(
        fields=["AREA_NAME", "university_zone"],
        aliases=["Neighbourhood:", "University Zone:"],
        style="font-size: 12px;",
    ),
).add_to(m)

# University markers
for uni_name, uni_info in UNIVERSITIES.items():
    folium.Marker(
        location=[uni_info["lat"], uni_info["lon"]],
        popup=uni_name,
        icon=folium.Icon(color="red", icon="university", prefix="fa"),
    ).add_to(m)

# Place markers as GeoJSON (fast)
for place_type in selected_types:
    type_data = filtered[filtered["place_type"] == place_type]
    if len(type_data) == 0:
        continue
    color    = PLACE_COLORS[place_type]
    features = []
    for _, row in type_data.iterrows():
        wifi_status = "Yes" if row.get("nearby_wifi", False) else "No"
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            "properties": {
                "name":    str(row.get("name",    "N/A")).replace('"', "'"),
                "type":    place_type.title(),
                "cost":    str(row.get("cost",    "N/A")).title(),
                "wifi":    wifi_status,
                "address": str(row.get("address", "N/A")).replace('"', "'"),
            },
        })
    folium.GeoJson(
        {"type": "FeatureCollection", "features": features},
        name=place_type.title(),
        marker=folium.CircleMarker(radius=4, fill=True, fill_opacity=0.7, weight=1),
        style_function=lambda feature, c=color: {
            "color": c, "fillColor": c,
            "radius": 4, "weight": 1, "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["name", "type", "cost", "wifi", "address"],
            aliases=["Name:", "Type:", "Cost:", "WiFi Nearby:", "Address:"],
            style="font-size: 11px;",
        ),
    ).add_to(m)

# Render map — return last_clicked for neighbourhood detection
map_data = st_folium(m, width=None, height=600, returned_objects=["last_clicked"])


# ============================================================
# Legend  (Improvement 2 colour squares + Improvement 3 blue-box note)
# ============================================================
st.markdown(
    """
    <div style="font-size:13px; color:#aaa; margin:4px 0 8px 0;">
      <span style="display:inline-block; width:13px; height:13px;
                   border:2px solid #000000; background:rgba(0,0,0,0.08);
                   vertical-align:middle; margin-right:5px;"></span>
      Selected Neighbourhood — click any area on the map to see details below
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# Neighbourhood Detail Panel  (Improvement 4)
# ============================================================
# Update session state when a new click is detected
if map_data and map_data.get("last_clicked"):
    click = map_data["last_clicked"]
    if click != st.session_state.get("_last_click_raw"):
        st.session_state["_last_click_raw"] = click
        # Point-in-polygon lookup
        click_pt = gpd.GeoDataFrame(
            geometry=[Point(click["lng"], click["lat"])], crs="EPSG:4326"
        )
        result = gpd.sjoin(
            click_pt,
            neighbourhoods[["AREA_NAME", "AREA_SHORT_CODE", "geometry"]],
            how="left",
            predicate="within",
        )
        if len(result) > 0 and pd.notna(result.iloc[0].get("AREA_NAME")):
            st.session_state["selected_hood"] = {
                "name": result.iloc[0]["AREA_NAME"],
                "code": normalize_hood(result.iloc[0]["AREA_SHORT_CODE"]),
            }
        else:
            st.session_state["selected_hood"] = None

# Display detail panel if a neighbourhood is selected
hood = st.session_state.get("selected_hood")
if hood:
    st.markdown("---")
    st.subheader(f"Neighbourhood Detail: {hood['name']}")

    # --- Place counts ---
    places_with_hood = get_places_with_hood()
    hood_places = places_with_hood[
        places_with_hood["hood_code"].apply(normalize_hood) == hood["code"]
    ]

    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    p_col1.metric("Total",     len(hood_places))
    p_col2.metric("Parks",     len(hood_places[hood_places["place_type"] == "park"]))
    p_col3.metric("Cafes",     len(hood_places[hood_places["place_type"] == "cafe"]))
    p_col4.metric("Libraries", len(hood_places[hood_places["place_type"] == "library"]))

    # --- Crime summary linked to year range ---
    crime_hood = crime_df[
        (crime_df["HOOD_158"].apply(normalize_hood) == hood["code"]) &
        (crime_df["OCC_YEAR"] >= year_range[0]) &
        (crime_df["OCC_YEAR"] <= year_range[1])
    ]
    crime_hood_agg = (
        crime_hood.groupby("MCI_CATEGORY")["count"]
        .sum()
        .reset_index()
        .sort_values("count", ascending=False)
    )

    st.caption(
        f"Crime incidents in **{hood['name']}** from **{year_range[0]}** to **{year_range[1]}** "
        f"(adjust the Year Range slider in the sidebar to update)"
    )

    if len(crime_hood_agg) > 0:
        fig_hood = px.bar(
            crime_hood_agg,
            x="MCI_CATEGORY",
            y="count",
            color="MCI_CATEGORY",
            title=f"Crime in {hood['name']} ({year_range[0]}–{year_range[1]})",
            labels={"MCI_CATEGORY": "Crime Category", "count": "Incident Count"},
            color_discrete_map=CRIME_COLORS,
        )
        fig_hood.update_layout(showlegend=False, xaxis_tickangle=-25, height=350)
        st.plotly_chart(fig_hood, use_container_width=True)
    else:
        st.info(f"No crime data recorded for {hood['name']} in this period.")



# ============================================================
# Footer
# ============================================================
st.markdown("---")
st.caption(
    "Data sources: [City of Toronto Open Data Portal](https://open.toronto.ca/) | "
    "[Toronto Police Service Public Safety Data Portal](https://data.torontopolice.on.ca/)"
)
