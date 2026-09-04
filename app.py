import streamlit as st
import json
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
    
    # Must use capital X-API-Key as shown in the OpenWebNinja documentation
    headers = {"X-API-Key": api_key}
    
    # OpenWebNinja requires a combined 'location' parameter
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
    target_city = st.text_input("City", value="Los Angeles")
with col2:
    target_state = st.text_input("State (Abbreviation)", value="CA", max_chars=2)

# 5. Strict Execution Lock
if st.button("Fetch & Verify Leads"):
    
    if run_mode == "TEST (Local Offline Data)":
        try:
            raw_data = load_fixture("mock_open_ninja_leads.json")
            st.success("Loaded offline fixture data successfully.")
            st.json(raw_data)
        except FileNotFoundError:
            st.error("Mock data file not found yet. Run a single LIVE query first to generate a raw JSON save file.")
            
    elif run_mode == "LIVE (External APIs)":
        
        if "RapidAPI" in api_source:
            st.error("RapidAPI quota maxed. Cooldown active until September 23rd. Switch to an OpenWebNinja source.")
            
        else:
            with st.spinner(f"Querying {api_source} for {target_city}, {target_state}..."):
                raw_data, status_msg = fetch_open_web_ninja_leads(api_source, target_city, target_state)
                
                if raw_data:
                    st.success(f"Success! {status_msg}")
                    st.json(raw_data)
                else:
                    st.error(status_msg)
