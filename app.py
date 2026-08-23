import streamlit as st
import pandas as pd
import requests
import re
import difflib
from urllib.parse import quote_plus

# --- CONFIGURATION & PAGE LAYOUT ---
st.set_page_config(page_title="Autonomous B2B Lead Engine", page_icon="🏢", layout="wide")

st.title("🏢 Autonomous Real-Estate Lead Engine")
st.markdown("Features: **Fuzzy Typo Correction | Dual-View UI | Algorithmic Verification**")

# --- SECRETS MANAGEMENT ---
try:
    RAPIDAPI_KEY = st.secrets["RAPIDAPI_KEY"]
except KeyError:
    st.error("⚠️ Critical Error: RapidAPI key missing in Streamlit secrets.toml.")
    st.stop()

# --- FUZZY MATCHING & DICTIONARIES ---
KNOWN_CITIES = [
    "Austin", "Dallas", "Houston", "San Antonio", "Fort Worth", "El Paso", 
    "Arlington", "Corpus Christi", "Plano", "Lubbock", "Miami", "Orlando", 
    "Tampa", "Atlanta", "Phoenix", "Denver", "Seattle", "Chicago", "New York"
]

STATE_MAPPINGS = {
    "TEXAS": "TX", "CALIFORNIA": "CA", "FLORIDA": "FL", "NEW YORK": "NY",
    "GEORGIA": "GA", "ARIZONA": "AZ", "COLORADO": "CO", "WASHINGTON": "WA"
}

def autocorrect_location(city_input, state_input):
    raw_city = str(city_input).strip().title()
    raw_state = str(state_input).strip().upper()
    clean_state = STATE_MAPPINGS.get(raw_state, raw_state[:2] if len(raw_state) >= 2 else "TX")
    matches = difflib.get_close_matches(raw_city, KNOWN_CITIES, n=1, cutoff=0.6)
    clean_city = matches[0] if matches else raw_city
    return clean_city, clean_state

# --- 100% PYTHON VALIDATION ENGINE ---
def is_valid_lead(address, prop_type, status):
    addr_upper = str(address).strip().upper()
    prop_type = str(prop_type).strip().upper()
    status = str(status).strip().upper()
    
    if not addr_upper or addr_upper in ['N/A', 'NONE', 'UNKNOWN']: return False
    if not re.match(r'^\d+\s+', addr_upper): return False
        
    blacklist = ['PLAN', 'FLOORPLAN', 'HOMESITE', 'COLLECTION AT', 'TRADITIONAL HOMES', 'ELEVATION', 'LOT ', 'VACANT', 'ACRE', 'PARCEL', 'UNRESTRICTED', 'TBD']
    if any(kw in addr_upper for kw in blacklist): return False
            
    invalid_types = ['LOT', 'LAND', 'VACANT_LAND', 'MANUFACTURED', 'MOBILE']
    if any(inv_type in prop_type for inv_type in invalid_types): return False

    inactive_statuses = ['OFF_MARKET', 'SOLD', 'PENDING', 'CLOSED', 'UNDER_CONTRACT']
    if any(bad_status in status for bad_status in inactive_statuses): return False
        
    return True

# --- DATA ENRICHMENT ---
def generate_contact_enrichment(address, city, state):
    query = quote_plus(f"{address}, {city}, {state} listing agent owner contact phone email")
    return f"https://www.google.com/search?q={query}"

# --- API INGESTION ENGINE ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_rapidapi_data_paginated(city, state, min_price, total_pages=3):
    location = f"{city}, {state}"
    url = "https://real-time-real-estate-data.p.rapidapi.com/search"
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": "real-time-real-estate-data.p.rapidapi.com"}
    all_leads = []
    
    for page in range(1, total_pages + 1):
        querystring = {"location": location, "sort": "NEWEST", "page": str(page)}
        try:
            response = requests.get(url, headers=headers, params=querystring, timeout=12)
            if response.status_code != 200: break
                
            data = response.json()
            data_payload = data.get("data", [])
            listings = data_payload.get("listings", []) if isinstance(data_payload, dict) else data_payload
            if not listings: break
                
            for item in listings:
                price = item.get("price", 0)
                if isinstance(price, str): 
                    price = int(''.join(filter(str.isdigit, price))) if any(c.isdigit() for c in price) else 0

                address = item.get("address", item.get("streetAddress", "N/A"))
                prop_type = item.get("homeType", item.get("propertyType", "SINGLE_FAMILY"))
                status = item.get("listingStatus", item.get("status", "ACTIVE"))

                if price >= min_price and is_valid_lead(address, prop_type, status):
                    mls_id = item.get("zpid", item.get("id", "N/A"))
                    agent_name = item.get("brokerName", item.get("agentName", "Listing Broker/Agent"))
                    
                    all_leads.append({
                        "Lead ID": f"MLS-{mls_id}",
                        "Address": address,
                        "City": city,
                        "State": state,
                        "Property Type": prop_type,
                        "Price ($)": price,
                        "Broker / Agent": agent_name,
                        "Listing URL": item.get("url", f"https://www.google.com/search?q={quote_plus(address)}"),
                        "Contact Lookup URL": generate_contact_enrichment(address, city, state)
                    })
        except Exception:
            break
            
    return pd.DataFrame(all_leads)

# --- SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("⚙️ Target Parameters")
    input_city = st.text_input("Target City", value="Austn")
    input_state = st.text_input("Target State", value="Texas", max_chars=10)
    min_price_threshold = st.number_input("Minimum Price ($)", min_value=10000, value=300000, step=50000)
    pages_to_crawl = st.slider("Depth (Pages to Crawl)", min_value=1, max_value=5, value=3)
    st.markdown("---")
    execute_search = st.button("🚀 Fetch & Enrich Leads", use_container_width=True)

# --- PIPELINE EXECUTION ---
if execute_search:
    st.cache_data.clear()
    
    clean_city, clean_state = autocorrect_location(input_city, input_state)
    if clean_city != input_city or clean_state != input_state:
        st.info(f"💡 **Fuzzy Correction Applied:** Input corrected to **{clean_city}, {clean_state}**.")
    
    with st.spinner(f"Querying {pages_to_crawl} page(s) of active listings for {clean_city}, {clean_state}..."):
        df = fetch_rapidapi_data_paginated(clean_city, clean_state, min_price_threshold, total_pages=pages_to_crawl)
        
        if df.empty:
            st.warning("⚠️ No qualified listings found. Try adjusting parameters.")
        else:
            df = df.drop_duplicates(subset=["Address"]).sort_values(by="Price ($)", ascending=False)
            
            # Metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Verified Leads", len(df))
            col2.metric("Pipeline Value", f"${int(df['Price ($)'].sum()):,}")
            col3.metric("Average Value", f"${int(df['Price ($)'].mean()):,}")
            col4.metric("Engine Pages", pages_to_crawl)
            st.markdown("---")
            
            csv_bytes = df.to_csv(index=False).encode('utf-8')
            
            # Dual-View UI
            tab_grid, tab_table = st.tabs(["🃏 Property Block View", "📊 Master Data Table"])
            
            # BLOCK VIEW
            with tab_grid:
                st.download_button("📥 Export These Leads to CSV", data=csv_bytes, file_name=f"{clean_city}_{clean_state}_Leads.csv", mime="text/csv", use_container_width=True)
                st.markdown("---")
                
                cols_per_row = 2 
                cols = st.columns(cols_per_row)
                
                for idx, row in df.reset_index(drop=True).iterrows():
                    col_idx = idx % cols_per_row
                    with cols[col_idx]:
                        with st.container(border=True):
                            st.markdown(f"#### ${row['Price ($)']:,}")
                            st.markdown(f"**📍 Address:** {row['Address']}")
                            st.markdown(f"**🏠 Type:** {row['Property Type']}")
                            st.markdown(f"**🏢 Broker:** {row['Broker / Agent']}")
                            
                            btn_col1, btn_col2 = st.columns(2)
                            with btn_col1:
                                st.link_button("🌐 Listing", row['Listing URL'], use_container_width=True)
                            with btn_col2:
                                st.link_button("🔍 Contact", row['Contact Lookup URL'], use_container_width=True)
            
            # TABLE VIEW
            with tab_table:
                st.download_button("📥 Download Master CSV Table", data=csv_bytes, file_name=f"{clean_city}_{clean_state}_MasterTable.csv", mime="text/csv", use_container_width=True)
                st.dataframe(df.style.format({"Price ($)": "${:,.0f}"}), use_container_width=True)
else:
    st.info("👈 Enter your target area and click **Fetch & Enrich Leads**.")
