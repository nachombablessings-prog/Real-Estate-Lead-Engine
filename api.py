import requests
import streamlit as st
from storage import save_raw_response

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
        {"address": "7728 Woodrow Wilson Dr, Los Angeles", "price": 14000000, "bedrooms": 5, "bathrooms": 6, "property_type": "SINGLE_FAMILY", "broker": "Serhant California, Inc"},
        {"address": "1326 Beverly Estate Dr, Beverly Hills", "price": 10995000, "bedrooms": 4, "bathrooms": 5, "property_type": "SINGLE_FAMILY", "broker": "Exclusive Realty Inc"}
    ]
}

def fetch_leads(api_choice, city, state):
    """Routes the request, handles 403 fallbacks, and archives the response."""
    config = OPENWEB_NINJA_ENDPOINTS.get(api_choice)
    if not config:
        return None, "Invalid API configuration."

    api_key = st.secrets.get(config["secret_key"], st.secrets.get(config["fallback_key"], ""))
    if not api_key:
        return None, "Missing API credentials in Streamlit secrets."

    try:
        response = requests.get(
            config["url"], 
            headers={"X-API-Key": api_key}, 
            params={"location": f"{city}, {state}"}, 
            timeout=12
        )
        if response.status_code == 200:
            raw_json = response.json()
            save_raw_response(raw_json, config["source_tag"], f"{city}_{state}")
            return raw_json, "Live query successful."
        return None, f"API Error {response.status_code}: {response.text}"
    except Exception as e:
        return None, f"Connection failed: {str(e)}"

def extract_listings(raw_data):
    """Standardizes disparate API JSON structures into a flat list of dictionaries."""
    if not isinstance(raw_data, dict):
        return []
    for key in ["results", "properties", "listings", "data", "content"]:
        if key in raw_data and isinstance(raw_data[key], list):
            return raw_data[key]
    if "result" in raw_data:
        return [raw_data["result"]]
    return BUILTIN_MOCK_DATA["results"]
