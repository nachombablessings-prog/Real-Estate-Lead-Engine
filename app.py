import streamlit as st
import json
import requests
from database import initialize_database
from storage import load_fixture, save_raw_response

# 1. Initialize the SQLite database immediately on boot
initialize_database()

# 2. Open Ninja API Fetcher (with Priority 2 Raw Archiving)
def fetch_open_ninja_leads(city, state):
    # Pull key securely from Streamlit Cloud Secrets
    OPEN_NINJA_KEY = st.secrets.get("OPEN_NINJA_KEY", "")
    
    if not OPEN_NINJA_KEY:
        return None, "Missing OPEN_NINJA_KEY in Streamlit app secrets."

    url = "https://api.api-ninjas.com/v1/realestate"
    headers = {"X-Api-Key": OPEN_NINJA_KEY}
    params = {"city": city, "state": state}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=12)
        
        if response.status_code == 200:
            raw_json = response.json()
            
            # Immediately save raw payload to local storage before any processing
            filepath = save_raw_response(
                data=raw_json, 
                source="open_ninja", 
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
st.markdown("Engine 1: Open Ninja | Engine 2: RapidAPI (Cooldown) | Engine 3: Local SQLite")

st.sidebar.header("System Settings")

run_mode = st.sidebar.radio(
    "Execution Mode:", 
    ["TEST (Local Offline Data)", "LIVE (External APIs)"]
)

api_source = st.sidebar.selectbox(
    "Live API Source:",
    ["Open Ninja (Primary)", "RapidAPI (Secondary - Cooldown)"]
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

# 5. Strict Execution Lock (Prevents auto-execution on page reload)
if st.button("Fetch & Verify Leads"):
    
    if run_mode == "TEST (Local Offline Data)":
        try:
            raw_data = load_fixture("mock_open_ninja_leads.json")
            st.success("Loaded offline fixture data successfully.")
            st.json(raw_data)
        except FileNotFoundError:
            st.error("Mock data file not found yet. Run a single LIVE query first to generate a raw JSON save file.")
            
    elif run_mode == "LIVE (External APIs)":
        
        if api_source == "RapidAPI (Secondary - Cooldown)":
            st.error("RapidAPI quota maxed. Cooldown active until September 23rd. Switch Engine to Open Ninja.")
            
        elif api_source == "Open Ninja (Primary)":
            with st.spinner(f"Querying Open Ninja for {target_city}, {target_state}..."):
                raw_data, status_msg = fetch_open_ninja_leads(target_city, target_state)
                
                if raw_data:
                    st.success(f"Success! {status_msg}")
                    st.json(raw_data)
                else:
                    st.error(status_msg)
