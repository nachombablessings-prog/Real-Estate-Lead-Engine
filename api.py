import requests
import streamlit as st
from storage import save_raw_response

# Primary Endpoint Configuration
OPENWEB_NINJA_ENDPOINTS = {
    "OpenWebNinja: Real Estate Data": {
        "url": "https://api.openwebninja.com/realtime-real-estate-data/zillow/search", 
        "secret_key": "OPEN_NINJA_REALESTATE_KEY",
        "source_tag": "openwebninja_realestate"
    }
}

def fetch_leads(api_choice, city, state):
    """Routes network requests for verified active real estate endpoints."""
    config = OPENWEB_NINJA_ENDPOINTS.get(api_choice)
    if not config:
        return None, "Invalid API configuration."

    api_key = st.secrets.get(config["secret_key"], "")
    if not api_key:
        return None, "Missing API credentials in Streamlit secrets."

    url = config["url"]
    headers = {"X-API-Key": api_key}
    params = {"location": f"{city}, {state}"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=12)
        
        if response.status_code == 200:
            raw_json = response.json()
            save_raw_response(raw_json, config["source_tag"], f"{city}_{state}")
            return raw_json, "Live query successful."
        elif response.status_code == 403:
            return None, "403 Forbidden: Invalid or unauthorized API key."
        else:
            return None, f"API Error {response.status_code}: {response.text}"
            
    except Exception as e:
        return None, f"Connection failed: {str(e)}"

def extract_listings(raw_data):
    """Safely parses JSON property keys without breaking on unexpected schema changes."""
    if not isinstance(raw_data, dict):
        return []
    for key in ["results", "properties", "listings", "data", "content"]:
        if key in raw_data and isinstance(raw_data[key], list):
            return raw_data[key]
    if "result" in raw_data:
        return [raw_data["result"]]
    return []
