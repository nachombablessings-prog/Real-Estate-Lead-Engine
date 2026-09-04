import streamlit as st
import json
import pandas as pd
import requests
from database import initialize_database
from storage import load_fixture, save_raw_response

# 1. Initialize the SQLite database immediately on boot
initialize_database()

# 2. Define exact OpenWebNinja endpoints and headers from your dashboard specs
OPENWEB_NINJA_ENDPOINTS = {
    "OpenWebNinja: Real Estate Data": {
        "url": "https://api.openwebninja.com/realtime-real-estate-data/zillow/search", 
        "secret_key": "OPEN_NINJA_REALESTATE_KEY",
        "source_tag": "openwebninja_realestate"
    },
    "OpenWebNinja: Redfin Data": {
        "url": "https://api.openwebninja.com/realtime-redfin-data/search", 
        "secret_key": "OPEN_NINJA_REDFIN_KEY",
        "source_tag": "openwebninja_redfin"
    }
}

def fetch_open_web_ninja_leads(api_choice, city, state):
    config = OPENWEB_NINJA_ENDPOINTS.get(api_choice)
    if not config:
        return None, "Invalid API configuration chosen."

    api_key = st.secrets.get(config["secret_key"], "")
    
    if not api_key:
        return None, f"Missing `{config['secret_key']}` in Streamlit app secrets."

    url = config["url"]
    headers = {"X-API-Key": api_key}
    params = {"location": f"{city}, {state}"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=12)
        
        if response.status_code == 200:
            raw_json = response.json()
            filepath = save_raw_response(
                data=raw_json, 
                source=config["source_tag"], 
                location=f"{city}_{state}"
            )
            return raw_json, f"Raw data safely archived to {filepath}"
        else:
            return None, f"API Error {response.status_code}: {response.text}"
            
    except Exception as e:
        return None, f"Connection failed: {str(e)}"

def render_leads_ui(raw_data):
    """Parses raw JSON and displays clean tables and structural blocks instead of code."""
    st.success("Data successfully loaded and formatted.")
    
    # Attempt to extract property listings from common keys in real estate payloads
    listings = []
    if isinstance(raw_data, dict):
        # Look through common keys where APIs store results
        for key in ["results", "properties", "listings", "data", "content"]:
            if key in raw_data and isinstance(raw_data[key], list):
                listings = raw_data[key]
                break
        # If no standard key matches, check if the dict itself can be items
        if not listings and "result" in raw_data:
            listings = [raw_data["result"]]

    if listings:
        st.subheader(f"Found {len(listings)} Property Listings")
        
        # Convert to DataFrame for clean tabular layout
        df = pd.DataFrame(listings)
        
        # Select key columns if they exist to make the table hyper-clean
        preferred_cols = ["address", "price", "bedrooms", "bathrooms", "property_type", "listing_status"]
        available_cols = [col for col in preferred_cols if col in df.columns]
        
        if available_cols:
            st.dataframe(df[available_cols], use_container_width=True)
        else:
            st.dataframe(df, use_container_width=True)
            
        # Display individual property blocks
        st.markdown("---")
        st.subheader("Detailed Property Blocks")
        for idx, item in enumerate(listings[:10]):  # Show top 10 as structured blocks
            with st.container():
                cols = st.columns([3, 1])
                with cols[0]:
                    st.markdown(f"**Property #{idx+1}: {item.get('address', 'Address Unavailable')}**")
                    st.write(f"Price: {item.get('price', 'N/A')} | Type: {item.get('property_type', 'N/A')}")
                with cols[1]:
                    st.metric("Beds / Baths", f"{item.get('bedrooms', '-')} / {item.get('bathrooms', '-')}")
                st.markdown("---")
    else:
        # Fallback if structure is unique
        st.warning("Rendered raw dictionary structure:")
        st.json(raw_data)

# 3. UI and System Configuration
st.set_page_config(page_title="Lead Engine V2", layout="wide")
st.title("Autonomous Real-Estate Lead Engine — V2")
st.markdown("Engine 1: OpenWebNinja (Multi-Key Setup) | Engine 2: RapidAPI | Engine 3: Local SQLite")

st.sidebar.header("System Settings")

run_mode = st.sidebar.radio(
    "Execution Mode:", 
    ["TEST (Local Offline Data)", "LIVE (External APIs)"]
)

api_source = st.sidebar.selectbox(
    "Live API Source:",
    list(OPENWEB_NINJA_ENDPOINTS.keys()) + ["RapidAPI (Secondary - Cooldown)"]
)

if run_mode == "TEST (Local Offline Data)":
    st.sidebar.success("🟢 Offline Mode Active: Zero API calls will be made.")
else:
    st.sidebar.warning(f"🔴 Live Mode Active: Will route through {api_source}.")

# 4. Target Market Parameters
st.subheader("Target Market")
col1, col2 = st.columns(2)
with col1:
    target_city = st.text_input("City", value="Austin")
with col2:
    target_state = st.text_input("State (Abbreviation)", value="TX", max_chars=2)

# 5. Strict Execution Lock
if st.button("Fetch & Verify Leads"):
    
    if run_mode == "TEST (Local Offline Data)":
        try:
            # Look for fixture files in order of availability
            raw_data = load_fixture("mock_open_ninja_leads.json")
            render_leads_ui(raw_data)
        except FileNotFoundError:
            st.error("Mock data file not found (`mock_open_ninja_leads.json`). Save a successful raw JSON response into your `/data/fixtures/` folder to enable offline test mode.")
            
    elif run_mode == "LIVE (External APIs)":
        
        if "RapidAPI" in api_source:
            st.error("RapidAPI quota maxed. Cooldown active until September 23rd. Switch to an OpenWebNinja source.")
            
        else:
            with st.spinner(f"Querying {api_source} for {target_city}, {target_state}..."):
                raw_data, status_msg = fetch_open_web_ninja_leads(api_source, target_city, target_state)
                
                if raw_data:
                    st.success(status_msg)
                    render_leads_ui(raw_data)
                else:
                    st.error(status_msg)
