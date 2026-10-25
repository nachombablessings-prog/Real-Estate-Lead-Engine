import streamlit as st
import pandas as pd
from database import initialize_database, log_leads_to_db, cached_fetch, cache_report
from api import fetch_leads, extract_listings, OPENWEB_NINJA_ENDPOINTS
from storage import load_fixture
from ui import render_metrics_banner, render_property_blocks

# 1. Boot Sequence
st.set_page_config(page_title="Autonomous Real-Estate Lead Engine", layout="wide")
initialize_database()

# 2. Sidebar Settings
st.sidebar.header("Target Parameters")
target_city = st.sidebar.text_input("Target City", value="Los Angeles")
target_state = st.sidebar.text_input("Target State", value="CA", max_chars=2)
crawl_depth = st.sidebar.slider("Depth (Pages to Crawl)", 1, 10, 5)

st.sidebar.markdown("---")
st.sidebar.header("System Settings")
run_mode = st.sidebar.radio("Execution Mode:", ["LIVE (External APIs)", "TEST (Local Offline Data)"])
api_source = st.sidebar.selectbox("Live API Source:", list(OPENWEB_NINJA_ENDPOINTS.keys()))
force_refresh = st.sidebar.checkbox("Force refresh (uses an API credit)", value=False)

# Cache performance: shows how many API calls the cache has saved you
with st.sidebar.expander("Cache & quota report"):
    st.json(cache_report())

# 3. Main Header
st.title("Autonomous Real-Estate Lead Engine")
st.markdown("**Features:** Fuzzy Typo Correction | Dual-View UI | Algorithmic Verification")

# 4. Data Processing
raw_data = None

if run_mode == "TEST (Local Offline Data)":
    try:
        # Reads real JSON response archived locally on disk
        raw_data = load_fixture("mock_open_ninja_leads.json")
        st.info("🟢 Offline Test Mode Active: Loaded real JSON data from `data/fixtures/mock_open_ninja_leads.json`.")
    except FileNotFoundError:
        st.error("No local fixture found. Save a real JSON payload to `data/fixtures/mock_open_ninja_leads.json` to enable offline testing.")
else:
    if st.button("Fetch & Enrich Leads"):
        with st.spinner(f"Checking cache / querying API for {target_city}, {target_state}..."):
            # Read-first: only calls fetch_leads when the cache is missing or older than 48h
            raw_data, msg = cached_fetch(
                api_source, target_city, target_state, fetch_leads,
                force_refresh=force_refresh,
            )
            if raw_data:
                st.success(msg)
            else:
                st.error(msg)

# 5. UI Rendering
if raw_data:
    listings = extract_listings(raw_data)

    if listings:
        df = pd.DataFrame(listings)
        log_leads_to_db(listings, api_source if run_mode == "LIVE (External APIs)" else "Local Test File")
        render_metrics_banner(listings, crawl_depth)
        render_property_blocks(listings, df)
    else:
        st.warning("Data loaded, but no valid property array keys were found in the payload.")
