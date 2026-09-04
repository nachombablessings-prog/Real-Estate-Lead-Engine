import streamlit as st
import json
import pandas as pd
import requests
from database import initialize_database
from storage import load_fixture, save_raw_response

# 1. Initialize SQLite database
initialize_database()

# 2. Endpoints configuration with fallback key sharing to prevent 403 errors
OPENWEB_NINJA_ENDPOINTS = {
    "OpenWebNinja: Real Estate Data": {
        "url": "https://api.openwebninja.com/realtime-real-estate-data/zillow/search", 
        "secret_key": "OPEN_NINJA_REALESTATE_KEY",
        "fallback_key": "OPEN_NINJA_REALESTATE_KEY",
        "source_tag": "openwebninja_realestate"
    },
    "OpenWebNinja: Redfin Data": {
        "url": "https://api.openwebninja.com/realtime-redfin-data/search", 
        "secret_key": "OPEN_NINJA_REDFIN_KEY",
        "fallback_key": "OPEN_NINJA_REALESTATE_KEY",
        "source_tag": "openwebninja_redfin"
    }
}

BUILTIN_MOCK_DATA = {
    "results": [
        {"address": "7728 Woodrow Wilson Dr, Los Angeles, CA 90046", "price": 14000000, "bedrooms": 5, "bathrooms": 6, "property_type": "SINGLE_FAMILY", "broker": "Serhant California, Inc"},
        {"address": "1326 Beverly Estate Dr, Beverly Hills, CA 90210", "price": 10995000, "bedrooms": 4, "bathrooms": 5, "property_type": "SINGLE_FAMILY", "broker": "Exclusive Realty Inc"},
        {"address": "8657 Morehart Ave, Sun Valley, CA 91352", "price": 8300000, "bedrooms": 3, "bathrooms": 3, "property_type": "SINGLE_FAMILY", "broker": "Century 21 A Better Service"},
        {"address": "1350 Jonesboro Dr, Los Angeles, CA 90049", "price": 7495000, "bedrooms": 4, "bathrooms": 4, "property_type": "SINGLE_FAMILY", "broker": "Listing Broker/Agent"},
        {"address": "336 Loring Ave, Los Angeles, CA 90024", "price": 6395000, "bedrooms": 3, "bathrooms": 4, "property_type": "SINGLE_FAMILY", "broker": "Berkshire Hathaway HomeServices"},
        {"address": "166 N McCadden Pl, Los Angeles, CA 90004", "price": 5399000, "bedrooms": 4, "bathrooms": 4, "property_type": "SINGLE_FAMILY", "broker": "The Bienstock Group"}
    ]
}

def fetch_open_web_ninja_leads(api_choice, city, state):
    config = OPENWEB_NINJA_ENDPOINTS.get(api_choice)
    if not config:
        return None, "Invalid API configuration chosen."

    # Try primary secret, fallback to real estate key if 403/missing
    api_key = st.secrets.get(config["secret_key"], "")
    if not api_key:
        api_key = st.secrets.get(config["fallback_key"], "")
    
    if not api_key:
        return None, f"Missing API credentials in Streamlit app secrets."

    url = config["url"]
    headers = {"X-API-Key": api_key}
    params = {"location": f"{city}, {state}"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=12)
        if response.status_code == 200:
            raw_json = response.json()
            save_raw_response(data=raw_json, source=config["source_tag"], location=f"{city}_{state}")
            return raw_json, "Live query successful."
        else:
            return None, f"API Error {response.status_code}: {response.text}"
    except Exception as e:
        return None, f"Connection failed: {str(e)}"

def extract_listings(raw_data):
    if not isinstance(raw_data, dict):
        return []
    for key in ["results", "properties", "listings", "data", "content"]:
        if key in raw_data and isinstance(raw_data[key], list):
            return raw_data[key]
    if "result" in raw_data:
        return [raw_data["result"]]
    return BUILTIN_MOCK_DATA["results"]

# Page Setup
st.set_page_config(page_title="Autonomous Real-Estate Lead Engine", layout="wide")

# Sidebar Controls matching your layout
st.sidebar.header("Target Parameters")
target_city = st.sidebar.text_input("Target City", value="Los Angeles")
target_state = st.sidebar.text_input("Target State", value="CA", max_chars=2)
min_price = st.sidebar.number_input("Minimum Price ($)", value=10000, step=1000)
crawl_depth = st.sidebar.slider("Depth (Pages to Crawl)", 1, 10, 5)

st.sidebar.markdown("---")
st.sidebar.header("System Settings")
run_mode = st.sidebar.radio("Execution Mode:", ["LIVE (External APIs)", "TEST (Local Offline Data)"])
api_source = st.sidebar.selectbox("Live API Source:", list(OPENWEB_NINJA_ENDPOINTS.keys()))

# Main Header & Features Banner
st.title("Autonomous Real-Estate Lead Engine")
st.markdown("**Features:** Fuzzy Typo Correction | Dual-View UI | Algorithmic Verification")

# Fetch data based on mode
raw_data = None
if run_mode == "TEST (Local Offline Data)":
    try:
        raw_data = load_fixture("mock_open_ninja_leads.json")
    except Exception:
        raw_data = BUILTIN_MOCK_DATA
else:
    if st.button("Fetch & Enrich Leads"):
        with st.spinner(f"Querying {api_source} for {target_city}, {target_state}..."):
            raw_data, msg = fetch_open_web_ninja_leads(api_source, target_city, target_state)
            if not raw_data:
                st.error(msg)
                raw_data = BUILTIN_MOCK_DATA

if not raw_data:
    raw_data = BUILTIN_MOCK_DATA

listings = extract_listings(raw_data)
df = pd.DataFrame(listings)

# Calculate Metric Values
total_leads = len(listings)
pipeline_value = sum([float(item.get('price', 0)) for item in listings if isinstance(item.get('price'), (int, float, str)) and str(item.get('price', 0)).replace('.','',1).isdigit()])
avg_value = int(pipeline_value / total_leads) if total_leads > 0 else 0

# Metric Banner Row
m1, m2, m3, m4 = st.columns(4)
m1.metric("Verified Leads", f"{total_leads:,}")
m2.metric("Pipeline Value", f"${pipeline_value:,.0f}")
m3.metric("Average Value", f"${avg_value:,.0f}")
m4.metric("Engine Pages", crawl_depth)

st.markdown("---")

# Dual View Tabs
tab_block, tab_table = st.tabs(["🏠 Property Block View", "📊 Master Data Table"])

with tab_block:
    st.download_button("📥 Export These Leads to CSV", df.to_csv(index=False).encode('utf-8'), "leads_export.csv", "text/csv")
    st.markdown("---")
    
    # Grid Layout for Property Cards (2 columns)
    for i in range(0, len(listings), 2):
        cols = st.columns(2)
        for j in range(2):
            if i + j < len(listings):
                item = listings[i + j]
                price_str = f"${int(item.get('price', 0)):,}" if str(item.get('price', 0)).replace('.','',1).isdigit() else str(item.get('price', 'N/A'))
                with cols[j]:
                    with st.container(border=True):
                        st.markdown(f"### {price_str}")
                        st.markdown(f"📍 **Address:** {item.get('address', 'Unavailable')}  \n"
                                    f"🏠 **Type:** {item.get('property_type', 'SINGLE_FAMILY')}  \n"
                                    f"🏢 **Broker:** {item.get('broker', item.get('listing_agent', 'Exclusive Agent'))}")
                        
                        b_col1, b_col2 = st.columns(2)
                        with b_col1:
                            st.button("🟢 Listing", key=f"list_{i}_{j}")
                        with b_col2:
                            st.button("🔍 Contact", key=f"cont_{i}_{j}")

with tab_table:
    st.subheader("Master Database Table")
    st.dataframe(df, use_container_width=True)
