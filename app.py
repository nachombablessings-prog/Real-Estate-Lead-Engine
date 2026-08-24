import streamlit as st
import pandas as pd
import requests
import re
import difflib
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

# --- CONFIGURATION & PAGE LAYOUT ---
st.set_page_config(page_title="Autonomous B2B Lead Engine", page_icon="🏢", layout="wide")

st.title("🏢 Autonomous Real-Estate Lead Engine")
st.markdown("Features: **RapidAPI MLS + Unblockable RSS Backup Scraper**")

# --- SECRETS MANAGEMENT ---
RAPIDAPI_KEY = st.secrets.get("RAPIDAPI_KEY", None)

# --- FUZZY MATCHING & CITY MAPPING ---
CITY_SLUGS = {
    "Austin": "austin", "Dallas": "dallas", "Houston": "houston", 
    "San Antonio": "sanantonio", "Los Angeles": "losangeles", "Miami": "miami",
    "New York": "newyork", "Chicago": "chicago", "Phoenix": "phoenix"
}

def autocorrect_location(city_input):
    raw_city = str(city_input).strip().title()
    matches = difflib.get_close_matches(raw_city, list(CITY_SLUGS.keys()), n=1, cutoff=0.5)
    clean_city = matches[0] if matches else "Austin"
    return clean_city, CITY_SLUGS.get(clean_city, clean_city.lower().replace(" ", ""))

# --- 100% PYTHON VALIDATION ENGINE ---
def is_valid_lead(address, prop_type, status="ACTIVE"):
    addr_upper = str(address).strip().upper()
    prop_type = str(prop_type).strip().upper()
    
    if not addr_upper or addr_upper in ['N/A', 'NONE', 'UNKNOWN']: return False
    
    blacklist = ['PLAN', 'FLOORPLAN', 'HOMESITE', 'COLLECTION AT', 'ELEVATION', 'LOT ', 'VACANT', 'ACRE', 'PARCEL', 'WANTED']
    if any(kw in addr_upper for kw in blacklist): return False
            
    invalid_types = ['LOT', 'LAND', 'VACANT_LAND', 'MANUFACTURED', 'MOBILE']
    if any(inv_type in prop_type for inv_type in invalid_types): return False

    return True

# --- ENGINE 1: RAPIDAPI MLS ---
def fetch_rapidapi_data(city, state, min_price):
    if not RAPIDAPI_KEY: return pd.DataFrame()
    
    url = "https://real-time-real-estate-data.p.rapidapi.com/search"
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": "real-time-real-estate-data.p.rapidapi.com"}
    querystring = {"location": f"{city}, {state}", "sort": "NEWEST", "page": "1"}
    
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=8)
        if response.status_code != 200: return pd.DataFrame()
            
        data = response.json().get("data", {})
        listings = data.get("listings", []) if isinstance(data, dict) else data
        
        leads = []
        for item in listings:
            price = item.get("price", 0)
            if isinstance(price, str): price = int(''.join(filter(str.isdigit, price))) if any(c.isdigit() for c in price) else 0
            address = item.get("address", item.get("streetAddress", "N/A"))
            
            if price >= min_price and is_valid_lead(address, item.get("homeType", "SINGLE_FAMILY")):
                leads.append({
                    "Source": "RapidAPI (MLS)",
                    "Lead ID": f"MLS-{item.get('zpid', '0000')}",
                    "Address": address,
                    "City": city,
                    "Price ($)": price,
                    "Property Type": item.get("homeType", "RESIDENTIAL"),
                    "Listing URL": item.get("url", f"https://www.google.com/search?q={quote_plus(address)}")
                })
        return pd.DataFrame(leads)
    except Exception:
        return pd.DataFrame()

# --- ENGINE 2: UNBLOCKABLE OPEN RSS REAL-ESTATE SCRAPER ---
@st.cache_data(ttl=1800, show_spinner=False)
def scrape_rss_real_estate(city_slug, clean_city, min_price):
    """Direct RSS parsing - zero API keys required, unblockable backup engine."""
    rss_url = f"https://{city_slug}.craigslist.org/search/rea?format=rss&min_price={min_price}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        response = requests.get(rss_url, headers=headers, timeout=10)
        if response.status_code != 200: return pd.DataFrame()
        
        root = ET.fromstring(response.content)
        leads = []
        
        # Parse XML RSS items
        for idx, item in enumerate(root.findall('.//{http://purl.org/rss/1.0/}item')):
            title = item.find('{http://purl.org/rss/1.0/}title').text if item.find('{http://purl.org/rss/1.0/}title') is not None else ""
            link = item.find('{http://purl.org/rss/1.0/}link').text if item.find('{http://purl.org/rss/1.0/}link') is not None else ""
            
            # Extract price from title (e.g. "$450000 / 3br - 1850ft2 - Great Location")
            price_match = re.search(r'\$([0-9,]+)', title)
            price = int(price_match.group(1).replace(',', '')) if price_match else 0
            
            # Clean title into address string
            clean_title = re.sub(r'\$([0-9,]+)', '', title).strip(' -/|')
            
            if price >= min_price and is_valid_lead(clean_title, "RESIDENTIAL"):
                leads.append({
                    "Source": "Engine 2 (Open Scraper)",
                    "Lead ID": f"SCR-{idx+1000}",
                    "Address": clean_title[:45] if clean_title else f"Active Listing near {clean_city}",
                    "City": clean_city,
                    "Price ($)": price,
                    "Property Type": "REAL_ESTATE",
                    "Listing URL": link
                })
        return pd.DataFrame(leads)
    except Exception:
        return pd.DataFrame()

# --- SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("⚙️ Target Parameters")
    input_city = st.text_input("Target City", value="Austin")
    min_price_threshold = st.number_input("Minimum Price ($)", min_value=10000, value=300000, step=50000)
    st.markdown("---")
    execute_search = st.button("🚀 Fetch & Verify Leads", use_container_width=True)

# --- EXECUTION PIPELINE ---
if execute_search:
    st.cache_data.clear()
    clean_city, city_slug = autocorrect_location(input_city)
    
    with st.spinner(f"Running Dual Engines for {clean_city}..."):
        # Engine 1 Call (RapidAPI)
        df_rapid = fetch_rapidapi_data(clean_city, "TX", min_price_threshold)
        # Engine 2 Call (Open RSS Scraper Backup)
        df_scraper = scrape_rss_real_estate(city_slug, clean_city, min_price_threshold)
        
        # Combine Engines
        combined_df = pd.concat([df_rapid, df_scraper], ignore_index=True)
        
        if combined_df.empty:
            st.warning("⚠️ No qualified listings found. Try lowering the minimum price.")
        else:
            combined_df = combined_df.drop_duplicates(subset=["Address"]).sort_values(by="Price ($)", ascending=False)
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Verified Leads", len(combined_df))
            col2.metric("Pipeline Value", f"${int(combined_df['Price ($)'].sum()):,}")
            col3.metric("Avg Value", f"${int(combined_df['Price ($)'].mean()):,}")
            st.markdown("---")
            
            csv_bytes = combined_df.to_csv(index=False).encode('utf-8')
            
            tab_block, tab_table = st.tabs(["🃏 Property Block View", "📊 Master Data Table"])
            
            with tab_block:
                st.download_button("📥 Export CSV", data=csv_bytes, file_name=f"{clean_city}_Leads.csv", mime="text/csv", use_container_width=True)
                st.markdown("---")
                cols = st.columns(2)
                for idx, row in combined_df.reset_index(drop=True).iterrows():
                    with cols[idx % 2]:
                        with st.container(border=True):
                            st.caption(f"Source: {row['Source']}")
                            st.markdown(f"#### ${row['Price ($)']:,}")
                            st.markdown(f"**📍 Listing:** {row['Address']}")
                            st.link_button("🌐 View Direct Listing", row['Listing URL'], use_container_width=True)
                            
            with tab_table:
                st.download_button("📥 Download Master Table", data=csv_bytes, file_name=f"{clean_city}_Master.csv", mime="text/csv", use_container_width=True)
                st.dataframe(combined_df.style.format({"Price ($)": "${:,.0f}"}), use_container_width=True)
else:
    st.info("👈 Enter your target city and click **Fetch & Verify Leads**.")
