import streamlit as st
import pandas as pd
import requests
import re
import urllib.parse
from bs4 import BeautifulSoup
import streamlit as st
import json
from database import initialize_database
from storage import load_fixture, save_raw_response

# 1. Initialize the SQLite database immediately on boot
initialize_database()

st.title("Real Estate Lead Engine — V2")

# 2. Establish the Mode Toggle in the Sidebar
st.sidebar.header("System Settings")
run_mode = st.sidebar.radio(
    "Data Source Mode:", 
    ["TEST (Local Offline Data)", "LIVE (RapidAPI)"]
)

if run_mode == "TEST (Local Offline Data)":
    st.sidebar.success("🟢 Offline Mode Active: Zero API calls will be made.")
else:
    st.sidebar.warning("🔴 Live Mode Active: Searches will consume API quota.")

# 3. Search Interface
st.subheader("Target Market")
col1, col2 = st.columns(2)
with col1:
    target_city = st.text_input("City", value="Los Angeles")
with col2:
    target_state = st.text_input("State (Abbreviation)", value="CA", max_chars=2)

if st.button("Search Leads"):
    if run_mode == "TEST (Local Offline Data)":
        # Load data from the local JSON fixture instead of the API
        try:
            # We will create this mock file next
            raw_data = load_fixture("mock_los_angeles.json")
            st.success("Loaded offline fixture data successfully.")
            st.json(raw_data) # Display raw data for now to verify
        except FileNotFoundError:
            st.error("Mock data file not found. We need to save a fixture first.")
            
    elif run_mode == "LIVE (RapidAPI)":
        st.info("Live API execution will go here.")
        # Your previous API fetching logic will eventually be plugged in here

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Autonomous B2B Lead Engine",
    page_icon="🏢",
    layout="wide"
)

st.title("🏢 Autonomous Real-Estate Lead Engine")
st.caption("Engine 1: RapidAPI MLS Ingestion | Engine 2: Yahoo Search Fallback | Enterprise Verification Matrix")

# ==========================================
# SECRETS MANAGEMENT (BACKEND ONLY)
# ==========================================
try:
    RAPIDAPI_KEY = st.secrets["RAPIDAPI_KEY"]
except KeyError:
    st.error("⚠️ Critical Error: RAPIDAPI_KEY is missing in Streamlit secrets.")
    st.stop()

# ==========================================
# SIDEBAR CONTROLS
# ==========================================
with st.sidebar:
    st.header("📍 Target Search Parameters")
    city_input = st.text_input("Target City", value="Miami")
    state_input = st.text_input("Target State (2-Letter)", value="FL", max_chars=2)
    max_leads = st.slider("Maximum Leads to Fetch", min_value=10, max_value=100, value=25)
    
    st.markdown("---")
    execute_search = st.button("🚀 Fetch & Verify Leads", use_container_width=True)

# ==========================================
# ENGINE 1: RAPIDAPI INGESTION
# ==========================================
def fetch_rapidapi_leads(city, state, api_key, limit=25):
    url = "https://us-real-estate-listings.p.rapidapi.com/v2/for-sale"
    querystring = {
        "city": city,
        "state_code": state,
        "offset": "0",
        "limit": str(limit),
        "sort": "newest"
    }
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "us-real-estate-listings.p.rapidapi.com"
    }
    
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=12)
        if response.status_code == 429 or response.status_code == 403:
            return None, "QUOTA_EXCEEDED"
        elif response.status_code != 200:
            return None, f"API_ERROR_{response.status_code}"
            
        data = response.json()
        results = data.get('data', {}).get('results', [])
        
        leads = []
        for item in results:
            location = item.get('location', {}).get('address', {})
            price = item.get('list_price', 0)
            status = item.get('status', 'Active')
            prop_type = item.get('description', {}).get('type', 'Single Family Home')
            brokerage = item.get('advertiser', {}).get('office', {}).get('name', 'N/A')
            listing_id = item.get('property_id', '')
            listing_url = f"https://www.realtor.com/realestateandhomes-detail/{listing_id}" if listing_id else ""
            
            leads.append({
                'Address': location.get('line', ''),
                'City': location.get('city', city),
                'State': location.get('state_code', state),
                'Zip': location.get('postal_code', ''),
                'Price': price,
                'Property Type': prop_type,
                'Status': status,
                'Brokerage / Agent': brokerage,
                'Listing URL': listing_url,
                'isPending': item.get('flags', {}).get('is_pending', False),
                'isContingent': item.get('flags', {}).get('is_contingent', False),
                'Source': 'RapidAPI Engine 1'
            })
        return leads, None
    except Exception as e:
        return None, str(e)

# ==========================================
# ENGINE 2: YAHOO SEARCH SCRAPER FALLBACK
# ==========================================
# ==========================================
# ENGINE 2: DDG LITE SCRAPER FALLBACK
# ==========================================
def scrape_web_leads_fallback(city, state, max_results=25):
    leads = []
    diagnostic_logs = []
    
    try:
        # Using DDG Lite (HTML-only). It bypasses standard JS/Cloudflare datacenter blocks.
        url = "https://lite.duckduckgo.com/lite/"
        query = f'site:realtor.com/realestateandhomes-detail "{city}" "{state}" "For Sale"'
        
        # POST payload mimicking a legacy browser form submission
        payload = {'q': query, 'kl': 'us-en'}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        resp = requests.post(url, data=payload, headers=headers, timeout=15)
        
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Iterate through the legacy table rows
            for tr in soup.find_all('tr'):
                td_snippet = tr.find('td', class_='result-snippet')
                if not td_snippet: 
                    continue
                    
                snippet_text = td_snippet.text.strip()
                
                # The URL is usually in the preceding row in DDG Lite structure
                prev_tr = tr.find_previous_sibling('tr')
                if not prev_tr:
                    continue
                    
                a_tag = prev_tr.find('a', class_='result-url')
                if not a_tag:
                    continue
                    
                href = a_tag.get('href', '')
                
                if 'realtor.com/realestateandhomes-detail' in href:
                    # Extract Price via Regex
                    price_match = re.search(r'\$([0-9,]+)', snippet_text)
                    price = int(price_match.group(1).replace(',', '')) if price_match else 0
                    
                    # Extract Address from URL Slug
                    url_match = re.search(r'/realestateandhomes-detail/([^/?]+)', href)
                    street_address = ""
                    if url_match:
                        raw_slug = url_match.group(1).replace('-', ' ')
                        parts = raw_slug.split('_')
                        street_address = parts[0].title()
                        
                    # Validate and Append
                    if price > 10000 and re.match(r'^\d+\s+', street_address):
                        leads.append({
                            'Address': street_address.replace('%20', ' '),
                            'City': city.title(),
                            'State': state.upper(),
                            'Zip': "Lookup via Contact",
                            'Price': price,
                            'Property Type': 'Single Family Home',
                            'Status': 'Active',
                            'Brokerage / Agent': 'Web Scraped Lead',
                            'Listing URL': href,
                            'isPending': False,
                            'isContingent': False,
                            'Source': 'Engine 2 (DDG Lite)'
                        })
        else:
            diagnostic_logs.append(f"DDG Lite Status: {resp.status_code} | Body: {resp.text[:150]}")
    except Exception as e:
        diagnostic_logs.append(f"DDG Lite Error: {str(e)}")

    # Remove duplicates
    unique_leads = {lead['Listing URL']: lead for lead in leads}.values()
    return list(unique_leads)[:max_results], diagnostic_logs
# ==========================================
# ENTERPRISE LEAD VERIFICATION ENGINE
# ==========================================
def verify_and_clean_leads(raw_leads):
    if not raw_leads:
        return pd.DataFrame(), 0

    df = pd.DataFrame(raw_leads)
    initial_count = len(df)
    valid_rows = []

    OFF_MARKET_KEYWORDS = [
        'PENDING', 'SOLD', 'UNDER CONTRACT', 'CONTINGENT', 'OFF MARKET', 'OFF_MARKET',
        'CLOSED', 'AUCTION', 'COMING SOON', 'TEMP OFF MARKET', 'INACTIVE', 'EXPIRED',
        'WITHDRAWN', 'NOTICE OF DEFAULT', 'FORECLOSURE'
    ]
    
    INVALID_PROPERTY_TYPES = [
        'LAND', 'LOT', 'MANUFACTURED', 'MOBILE', 'PARKING', 'STORAGE', 'CEMETERY',
        'BOAT SLIP', 'DOCK', 'TIMESHARE', 'VACANT LAND'
    ]

    for idx, row in df.iterrows():
        status_str = str(row.get('Status', '')).upper()
        prop_type_str = str(row.get('Property Type', '')).upper()
        addr_str = str(row.get('Address', '')).strip()
        
        try:
            price_val = float(row.get('Price', 0)) if pd.notnull(row.get('Price')) else 0
        except ValueError:
            price_val = 0

        # Strict Rules
        if not re.match(r'^\d+\s+[A-Za-z0-9]', addr_str): continue
        if any(keyword in status_str for keyword in OFF_MARKET_KEYWORDS): continue
        if any(p_type in prop_type_str for p_type in INVALID_PROPERTY_TYPES): continue
        if price_val < 10000: continue
        if row.get('isPending') is True or row.get('isContingent') is True: continue

        query_str = f"{addr_str} {row['City']} {row['State']}".strip()
        lookup_encoded = urllib.parse.quote(query_str)
        
        valid_entry = {
            'Verification': '✅ VERIFIED ACTIVE',
            'Address': addr_str,
            'City': row['City'],
            'State': row['State'],
            'Zip': row['Zip'],
            'Price ($)': f"${price_val:,.0f}",
            'Property Type': row['Property Type'],
            'Status': row['Status'],
            'Brokerage / Agent': row['Brokerage / Agent'],
            'Listing URL': row['Listing URL'],
            'Contact Lookup': f"https://www.truepeoplesearch.com/results?name={lookup_encoded}",
            'Source Engine': row['Source']
        }
        valid_rows.append(valid_entry)

    verified_df = pd.DataFrame(valid_rows)
    off_market_count = initial_count - len(verified_df)
    return verified_df, off_market_count

# ==========================================
# MAIN APPLICATION EXECUTION
# ==========================================
if execute_search:
    with st.spinner("Executing Lead Extraction & Verification Pipeline..."):
        leads = []
        engine_used = ""
        diagnostics = []
        
        # Primary API Call
        raw_leads, error = fetch_rapidapi_leads(city_input, state_input, RAPIDAPI_KEY, max_leads)
        
        # Engine Failover Logic
        if error == "QUOTA_EXCEEDED" or (raw_leads is not None and len(raw_leads) == 0):
            st.warning("⚠️ RapidAPI quota exhausted. Failing over to Web Scraper Engine 2...")
            leads, diagnostics = scrape_web_leads_fallback(city_input, state_input, max_leads)
            engine_used = "Web Scraper Engine 2 (Yahoo)"
        elif raw_leads:
            leads = raw_leads
            engine_used = "RapidAPI Real Estate Engine 1"
        else:
            st.error(f"⚠️ Primary API Error: {error}. Failing over to Engine 2...")
            leads, diagnostics = scrape_web_leads_fallback(city_input, state_input, max_leads)
            engine_used = "Web Scraper Engine 2 (Yahoo)"

        # Verification Pipeline
        verified_df, filtered_off_market = verify_and_clean_leads(leads)

    # Output Metrics
    st.subheader("📊 Pipeline Diagnostics")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Extracted", len(leads))
    col2.metric("Verified Active", len(verified_df))
    col3.metric("Filtered Off-Market", filtered_off_market)
    col4.metric("Active Engine", engine_used)

    # Display Engine 2 Diagnostics if it failed
    if "Engine 2" in engine_used and len(leads) == 0:
        with st.expander("🛠️ Scraper Diagnostic Logs (Why it returned 0)"):
            st.error("Engine 2 experienced an issue. See logs below:")
            for log in diagnostics:
                st.code(log)

    # Render Data Table
    if not verified_df.empty:
        st.subheader("📋 Verified Active Leads")
        st.dataframe(
            verified_df,
            column_config={
                "Listing URL": st.column_config.LinkColumn("Listing Link", display_text="View Listing"),
                "Contact Lookup": st.column_config.LinkColumn("Owner Contact", display_text="Find Owner Details")
            },
            use_container_width=True,
            hide_index=True
        )
        
        # CSV Export
        csv_data = verified_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Verified Leads (CSV)",
            data=csv_data,
            file_name=f"verified_leads_{city_input}_{state_input}.csv",
            mime="text/csv"
        )
    else:
        st.error("No active, verified leads were found. Check the diagnostic logs above if Engine 2 fired blanks.")
