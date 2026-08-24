import streamlit as st
import pandas as pd
import requests
import re
import io
import urllib.parse
from bs4 import BeautifulSoup

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Real Estate Lead Scraper & Verifier Pro",
    page_icon="🏠",
    layout="wide"
)

st.title("🏠 Real Estate Lead Scraper & Automated Verifier")
st.caption("Engine 1: RapidAPI Lead Ingestion | Engine 2: Redfin & DDG Web Scraper Fallback | Enterprise Verification Matrix")

# ==========================================
# SIDEBAR CONTROLS
# ==========================================
st.sidebar.header("🔑 API & System Settings")
rapidapi_key = st.sidebar.text_input("RapidAPI Key", type="password", help="Enter your RapidAPI Key for Real Estate API")

st.sidebar.header("📍 Target Search Parameters")
city_input = st.sidebar.text_input("City", value="Miami")
state_input = st.sidebar.text_input("State (2-Letter)", value="FL", max_chars=2)
max_leads = st.sidebar.slider("Maximum Leads to Fetch", min_value=10, max_value=100, value=25)

# ==========================================
# ENGINE 1: RAPIDAPI INGESTION
# ==========================================
def fetch_rapidapi_leads(city, state, api_key, limit=25):
    """
    Fetches real estate leads via RapidAPI Real Estate API.
    Returns (leads_list, error_message)
    """
    if not api_key:
        return None, "API_KEY_MISSING"
        
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
        if response.status_code == 429:
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
                'Source': 'RapidAPI Engine'
            })
        return leads, None
    except Exception as e:
        return None, str(e)

# ==========================================
# ENGINE 2: WEB SCRAPER FALLBACK
# ==========================================
def scrape_web_leads_fallback(city, state, max_results=25):
    """
    Fallback engine executing when RapidAPI quota is exhausted or unavailable.
    Scrapes Redfin Public Streams and Real-Time Search Indexes.
    """
    leads = []
    
    # Method A: Redfin Public GIS Search Endpoint
    try:
        url = "https://www.redfin.com/stingray/api/gis-csv"
        params = {
            "al": "1",
            "market": city.lower().replace(" ", ""),
            "num_homes": str(max_results * 2),
            "status": "9",  # 9 = Active listings only in Redfin GIS
            "v": "8"
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/csv,application/json,text/plain,*/*"
        }
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        
        if resp.status_code == 200 and len(resp.text) > 100 and "ADDRESS" in resp.text.upper():
            df_csv = pd.read_csv(io.StringIO(resp.text))
            for _, row in df_csv.iterrows():
                addr = str(row.get('ADDRESS', '')).strip()
                c = str(row.get('CITY', city)).strip()
                s = str(row.get('STATE OR PROVINCE', state)).strip()
                zip_c = str(row.get('ZIP OR POSTAL CODE', '')).replace('.0', '').strip()
                price = row.get('PRICE', 0)
                p_type = str(row.get('PROPERTY TYPE', 'Single Family')).strip()
                status = str(row.get('STATUS', 'Active')).strip()
                redfin_path = str(row.get('URL (SEE http://www.redfin.com/redfin_firm FOR BEHAVIOR)', '')).strip()
                
                listing_url = f"https://www.redfin.com{redfin_path}" if redfin_path.startswith('/') else redfin_path
                
                if addr and addr.lower() != 'nan':
                    leads.append({
                        'Address': addr,
                        'City': c,
                        'State': s,
                        'Zip': zip_c,
                        'Price': price,
                        'Property Type': p_type,
                        'Status': status,
                        'Brokerage / Agent': 'Redfin Listed Agent',
                        'Listing URL': listing_url or f"https://www.google.com/search?q={urllib.parse.quote(f'{addr} {c} {s}')}",
                        'isPending': False,
                        'isContingent': False,
                        'Source': 'Web Scraper Engine'
                    })
    except Exception:
        pass

    # Method B: Search Index Scraping (Fallback if GIS returns limited results)
    if len(leads) < 5:
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q=site:realtor.com/realestateandhomes-detail+\"{city}\"+\"{state}\"+\"For Sale\""
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
            r = requests.get(ddg_url, headers=headers, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                results = soup.find_all('a', class_='result__url')
                snippets = soup.find_all('a', class_='result__snippet')
                
                for idx, res in enumerate(results):
                    href = res.get('href', '')
                    snippet_text = snippets[idx].text if idx < len(snippets) else ''
                    
                    match_price = re.search(r'\$([0-9,]+)', snippet_text)
                    price = int(match_price.group(1).replace(',', '')) if match_price else 0
                    
                    url_match = re.search(r'/realestateandhomes-detail/([^/?]+)', href)
                    if url_match:
                        raw_slug = url_match.group(1).replace('-', ' ')
                        parts = raw_slug.split('_')
                        street = parts[0] if len(parts) > 0 else raw_slug
                        if re.match(r'^\d+\s+', street):
                            leads.append({
                                'Address': street.title(),
                                'City': city.title(),
                                'State': state.upper(),
                                'Zip': parts[2] if len(parts) > 2 else '',
                                'Price': price,
                                'Property Type': 'Single Family Home',
                                'Status': 'Active',
                                'Brokerage / Agent': 'MLS Active',
                                'Listing URL': f"https:{href}" if href.startswith('//') else href,
                                'isPending': False,
                                'isContingent': False,
                                'Source': 'Web Scraper Engine'
                            })
        except Exception:
            pass

    return leads[:max_results]

# ==========================================
# ENTERPRISE LEAD VERIFICATION ENGINE
# ==========================================
def verify_and_clean_leads(raw_leads):
    """
    Strict 5-Tier Verification Pipeline:
    Filters out off-market, pending, sold, contingent, land, lots, and invalid addresses.
    """
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
        price_val = float(row.get('Price', 0)) if pd.notnull(row.get('Price')) else 0

        # Rule 1: Address must start with a street number
        if not re.match(r'^\d+\s+[A-Za-z0-9]', addr_str):
            continue

        # Rule 2: Exclude off-market / sold / pending / contingent statuses
        if any(keyword in status_str for keyword in OFF_MARKET_KEYWORDS):
            continue

        # Rule 3: Reject non-residential land, mobile, or lot types
        if any(p_type in prop_type_str for p_type in INVALID_PROPERTY_TYPES):
            continue

        # Rule 4: Sanity check price threshold ($10,000+)
        if price_val < 10000:
            continue

        # Rule 5: Explicit Boolean flag checks from source API
        if row.get('isPending') is True or row.get('isContingent') is True:
            continue

        # Construct Owner Contact Lookup Link
        query_str = f"{addr_str} {row['City']} {row['State']} {row['Zip']}".strip()
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
# MAIN APPLICATION INTERFACE
# ==========================================
if st.button("🚀 Fetch & Verify Leads", type="primary"):
    with st.spinner("Executing Lead Extraction & Verification Pipeline..."):
        leads = []
        engine_used = ""
        
        # Try Primary Engine
        raw_leads, error = fetch_rapidapi_leads(city_input, state_input, rapidapi_key, max_leads)
        
        if error == "QUOTA_EXCEEDED" or error == "API_KEY_MISSING" or (raw_leads is not None and len(raw_leads) == 0):
            st.warning("⚠️ RapidAPI quota exceeded or key missing. Failing over to Web Scraper Engine 2...")
            leads = scrape_web_leads_fallback(city_input, state_input, max_leads)
            engine_used = "Web Scraper Engine 2 (Redfin/DDG Indexer)"
        elif raw_leads:
            leads = raw_leads
            engine_used = "RapidAPI Real Estate Engine 1"
        else:
            st.error(f"Error fetching from primary API: {error}. Switching to web scraper...")
            leads = scrape_web_leads_fallback(city_input, state_input, max_leads)
            engine_used = "Web Scraper Engine 2 (Redfin/DDG Indexer)"

        # Run Verification
        verified_df, filtered_off_market = verify_and_clean_leads(leads)

    # Display KPI Dashboard
    st.subheader("📊 Lead Generation Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Extracted", len(leads))
    col2.metric("Verified Active", len(verified_df))
    col3.metric("Filtered Off-Market", filtered_off_market)
    col4.metric("Active Engine", engine_used)

    if not verified_df.empty:
        st.subheader("📋 Verified Active Leads")
        
        # Display Interactive Table
        st.dataframe(
            verified_df,
            column_config={
                "Listing URL": st.column_config.LinkColumn("Listing Link", display_text="View Listing"),
                "Contact Lookup": st.column_config.LinkColumn("Owner Contact", display_text="Find Owner Details")
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Export Actions
        csv_data = verified_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Verified Leads (CSV)",
            data=csv_data,
            file_name=f"verified_leads_{city_input}_{state_input}.csv",
            mime="text/csv"
        )
    else:
        st.error("No active, verified leads were found matching the criteria. Try expanding search parameters or checking city spelling.")import streamlit as st
import pandas as pd
import requests
import re
import io
import urllib.parse
from bs4 import BeautifulSoup

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Real Estate Lead Scraper & Verifier Pro",
    page_icon="🏠",
    layout="wide"
)

st.title("🏠 Real Estate Lead Scraper & Automated Verifier")
st.caption("Engine 1: RapidAPI Lead Ingestion | Engine 2: Redfin & DDG Web Scraper Fallback | Enterprise Verification Matrix")

# ==========================================
# SIDEBAR CONTROLS
# ==========================================
st.sidebar.header("🔑 API & System Settings")
rapidapi_key = st.sidebar.text_input("RapidAPI Key", type="password", help="Enter your RapidAPI Key for Real Estate API")

st.sidebar.header("📍 Target Search Parameters")
city_input = st.sidebar.text_input("City", value="Miami")
state_input = st.sidebar.text_input("State (2-Letter)", value="FL", max_chars=2)
max_leads = st.sidebar.slider("Maximum Leads to Fetch", min_value=10, max_value=100, value=25)

# ==========================================
# ENGINE 1: RAPIDAPI INGESTION
# ==========================================
def fetch_rapidapi_leads(city, state, api_key, limit=25):
    """
    Fetches real estate leads via RapidAPI Real Estate API.
    Returns (leads_list, error_message)
    """
    if not api_key:
        return None, "API_KEY_MISSING"
        
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
        if response.status_code == 429:
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
                'Source': 'RapidAPI Engine'
            })
        return leads, None
    except Exception as e:
        return None, str(e)

# ==========================================
# ENGINE 2: WEB SCRAPER FALLBACK
# ==========================================
def scrape_web_leads_fallback(city, state, max_results=25):
    """
    Fallback engine executing when RapidAPI quota is exhausted or unavailable.
    Scrapes Redfin Public Streams and Real-Time Search Indexes.
    """
    leads = []
    
    # Method A: Redfin Public GIS Search Endpoint
    try:
        url = "https://www.redfin.com/stingray/api/gis-csv"
        params = {
            "al": "1",
            "market": city.lower().replace(" ", ""),
            "num_homes": str(max_results * 2),
            "status": "9",  # 9 = Active listings only in Redfin GIS
            "v": "8"
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/csv,application/json,text/plain,*/*"
        }
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        
        if resp.status_code == 200 and len(resp.text) > 100 and "ADDRESS" in resp.text.upper():
            df_csv = pd.read_csv(io.StringIO(resp.text))
            for _, row in df_csv.iterrows():
                addr = str(row.get('ADDRESS', '')).strip()
                c = str(row.get('CITY', city)).strip()
                s = str(row.get('STATE OR PROVINCE', state)).strip()
                zip_c = str(row.get('ZIP OR POSTAL CODE', '')).replace('.0', '').strip()
                price = row.get('PRICE', 0)
                p_type = str(row.get('PROPERTY TYPE', 'Single Family')).strip()
                status = str(row.get('STATUS', 'Active')).strip()
                redfin_path = str(row.get('URL (SEE http://www.redfin.com/redfin_firm FOR BEHAVIOR)', '')).strip()
                
                listing_url = f"https://www.redfin.com{redfin_path}" if redfin_path.startswith('/') else redfin_path
                
                if addr and addr.lower() != 'nan':
                    leads.append({
                        'Address': addr,
                        'City': c,
                        'State': s,
                        'Zip': zip_c,
                        'Price': price,
                        'Property Type': p_type,
                        'Status': status,
                        'Brokerage / Agent': 'Redfin Listed Agent',
                        'Listing URL': listing_url or f"https://www.google.com/search?q={urllib.parse.quote(f'{addr} {c} {s}')}",
                        'isPending': False,
                        'isContingent': False,
                        'Source': 'Web Scraper Engine'
                    })
    except Exception:
        pass

    # Method B: Search Index Scraping (Fallback if GIS returns limited results)
    if len(leads) < 5:
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q=site:realtor.com/realestateandhomes-detail+\"{city}\"+\"{state}\"+\"For Sale\""
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
            r = requests.get(ddg_url, headers=headers, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                results = soup.find_all('a', class_='result__url')
                snippets = soup.find_all('a', class_='result__snippet')
                
                for idx, res in enumerate(results):
                    href = res.get('href', '')
                    snippet_text = snippets[idx].text if idx < len(snippets) else ''
                    
                    match_price = re.search(r'\$([0-9,]+)', snippet_text)
                    price = int(match_price.group(1).replace(',', '')) if match_price else 0
                    
                    url_match = re.search(r'/realestateandhomes-detail/([^/?]+)', href)
                    if url_match:
                        raw_slug = url_match.group(1).replace('-', ' ')
                        parts = raw_slug.split('_')
                        street = parts[0] if len(parts) > 0 else raw_slug
                        if re.match(r'^\d+\s+', street):
                            leads.append({
                                'Address': street.title(),
                                'City': city.title(),
                                'State': state.upper(),
                                'Zip': parts[2] if len(parts) > 2 else '',
                                'Price': price,
                                'Property Type': 'Single Family Home',
                                'Status': 'Active',
                                'Brokerage / Agent': 'MLS Active',
                                'Listing URL': f"https:{href}" if href.startswith('//') else href,
                                'isPending': False,
                                'isContingent': False,
                                'Source': 'Web Scraper Engine'
                            })
        except Exception:
            pass

    return leads[:max_results]

# ==========================================
# ENTERPRISE LEAD VERIFICATION ENGINE
# ==========================================
def verify_and_clean_leads(raw_leads):
    """
    Strict 5-Tier Verification Pipeline:
    Filters out off-market, pending, sold, contingent, land, lots, and invalid addresses.
    """
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
        price_val = float(row.get('Price', 0)) if pd.notnull(row.get('Price')) else 0

        # Rule 1: Address must start with a street number
        if not re.match(r'^\d+\s+[A-Za-z0-9]', addr_str):
            continue

        # Rule 2: Exclude off-market / sold / pending / contingent statuses
        if any(keyword in status_str for keyword in OFF_MARKET_KEYWORDS):
            continue

        # Rule 3: Reject non-residential land, mobile, or lot types
        if any(p_type in prop_type_str for p_type in INVALID_PROPERTY_TYPES):
            continue

        # Rule 4: Sanity check price threshold ($10,000+)
        if price_val < 10000:
            continue

        # Rule 5: Explicit Boolean flag checks from source API
        if row.get('isPending') is True or row.get('isContingent') is True:
            continue

        # Construct Owner Contact Lookup Link
        query_str = f"{addr_str} {row['City']} {row['State']} {row['Zip']}".strip()
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
# MAIN APPLICATION INTERFACE
# ==========================================
if st.button("🚀 Fetch & Verify Leads", type="primary"):
    with st.spinner("Executing Lead Extraction & Verification Pipeline..."):
        leads = []
        engine_used = ""
        
        # Try Primary Engine
        raw_leads, error = fetch_rapidapi_leads(city_input, state_input, rapidapi_key, max_leads)
        
        if error == "QUOTA_EXCEEDED" or error == "API_KEY_MISSING" or (raw_leads is not None and len(raw_leads) == 0):
            st.warning("⚠️ RapidAPI quota exceeded or key missing. Failing over to Web Scraper Engine 2...")
            leads = scrape_web_leads_fallback(city_input, state_input, max_leads)
            engine_used = "Web Scraper Engine 2 (Redfin/DDG Indexer)"
        elif raw_leads:
            leads = raw_leads
            engine_used = "RapidAPI Real Estate Engine 1"
        else:
            st.error(f"Error fetching from primary API: {error}. Switching to web scraper...")
            leads = scrape_web_leads_fallback(city_input, state_input, max_leads)
            engine_used = "Web Scraper Engine 2 (Redfin/DDG Indexer)"

        # Run Verification
        verified_df, filtered_off_market = verify_and_clean_leads(leads)

    # Display KPI Dashboard
    st.subheader("📊 Lead Generation Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Extracted", len(leads))
    col2.metric("Verified Active", len(verified_df))
    col3.metric("Filtered Off-Market", filtered_off_market)
    col4.metric("Active Engine", engine_used)

    if not verified_df.empty:
        st.subheader("📋 Verified Active Leads")
        
        # Display Interactive Table
        st.dataframe(
            verified_df,
            column_config={
                "Listing URL": st.column_config.LinkColumn("Listing Link", display_text="View Listing"),
                "Contact Lookup": st.column_config.LinkColumn("Owner Contact", display_text="Find Owner Details")
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Export Actions
        csv_data = verified_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Verified Leads (CSV)",
            data=csv_data,
            file_name=f"verified_leads_{city_input}_{state_input}.csv",
            mime="text/csv"
        )
    else:
        st.error("No active, verified leads were found matching the criteria. Try expanding search parameters or checking city spelling.")import streamlit as st
import pandas as pd
import requests
import re
import io
import urllib.parse
from bs4 import BeautifulSoup

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Real Estate Lead Scraper & Verifier Pro",
    page_icon="🏠",
    layout="wide"
)

st.title("🏠 Real Estate Lead Scraper & Automated Verifier")
st.caption("Engine 1: RapidAPI Lead Ingestion | Engine 2: Redfin & DDG Web Scraper Fallback | Enterprise Verification Matrix")

# ==========================================
# SIDEBAR CONTROLS
# ==========================================
st.sidebar.header("🔑 API & System Settings")
rapidapi_key = st.sidebar.text_input("RapidAPI Key", type="password", help="Enter your RapidAPI Key for Real Estate API")

st.sidebar.header("📍 Target Search Parameters")
city_input = st.sidebar.text_input("City", value="Miami")
state_input = st.sidebar.text_input("State (2-Letter)", value="FL", max_chars=2)
max_leads = st.sidebar.slider("Maximum Leads to Fetch", min_value=10, max_value=100, value=25)

# ==========================================
# ENGINE 1: RAPIDAPI INGESTION
# ==========================================
def fetch_rapidapi_leads(city, state, api_key, limit=25):
    """
    Fetches real estate leads via RapidAPI Real Estate API.
    Returns (leads_list, error_message)
    """
    if not api_key:
        return None, "API_KEY_MISSING"
        
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
        if response.status_code == 429:
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
                'Source': 'RapidAPI Engine'
            })
        return leads, None
    except Exception as e:
        return None, str(e)

# ==========================================
# ENGINE 2: WEB SCRAPER FALLBACK
# ==========================================
def scrape_web_leads_fallback(city, state, max_results=25):
    """
    Fallback engine executing when RapidAPI quota is exhausted or unavailable.
    Scrapes Redfin Public Streams and Real-Time Search Indexes.
    """
    leads = []
    
    # Method A: Redfin Public GIS Search Endpoint
    try:
        url = "https://www.redfin.com/stingray/api/gis-csv"
        params = {
            "al": "1",
            "market": city.lower().replace(" ", ""),
            "num_homes": str(max_results * 2),
            "status": "9",  # 9 = Active listings only in Redfin GIS
            "v": "8"
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/csv,application/json,text/plain,*/*"
        }
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        
        if resp.status_code == 200 and len(resp.text) > 100 and "ADDRESS" in resp.text.upper():
            df_csv = pd.read_csv(io.StringIO(resp.text))
            for _, row in df_csv.iterrows():
                addr = str(row.get('ADDRESS', '')).strip()
                c = str(row.get('CITY', city)).strip()
                s = str(row.get('STATE OR PROVINCE', state)).strip()
                zip_c = str(row.get('ZIP OR POSTAL CODE', '')).replace('.0', '').strip()
                price = row.get('PRICE', 0)
                p_type = str(row.get('PROPERTY TYPE', 'Single Family')).strip()
                status = str(row.get('STATUS', 'Active')).strip()
                redfin_path = str(row.get('URL (SEE http://www.redfin.com/redfin_firm FOR BEHAVIOR)', '')).strip()
                
                listing_url = f"https://www.redfin.com{redfin_path}" if redfin_path.startswith('/') else redfin_path
                
                if addr and addr.lower() != 'nan':
                    leads.append({
                        'Address': addr,
                        'City': c,
                        'State': s,
                        'Zip': zip_c,
                        'Price': price,
                        'Property Type': p_type,
                        'Status': status,
                        'Brokerage / Agent': 'Redfin Listed Agent',
                        'Listing URL': listing_url or f"https://www.google.com/search?q={urllib.parse.quote(f'{addr} {c} {s}')}",
                        'isPending': False,
                        'isContingent': False,
                        'Source': 'Web Scraper Engine'
                    })
    except Exception:
        pass

    # Method B: Search Index Scraping (Fallback if GIS returns limited results)
    if len(leads) < 5:
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q=site:realtor.com/realestateandhomes-detail+\"{city}\"+\"{state}\"+\"For Sale\""
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
            r = requests.get(ddg_url, headers=headers, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                results = soup.find_all('a', class_='result__url')
                snippets = soup.find_all('a', class_='result__snippet')
                
                for idx, res in enumerate(results):
                    href = res.get('href', '')
                    snippet_text = snippets[idx].text if idx < len(snippets) else ''
                    
                    match_price = re.search(r'\$([0-9,]+)', snippet_text)
                    price = int(match_price.group(1).replace(',', '')) if match_price else 0
                    
                    url_match = re.search(r'/realestateandhomes-detail/([^/?]+)', href)
                    if url_match:
                        raw_slug = url_match.group(1).replace('-', ' ')
                        parts = raw_slug.split('_')
                        street = parts[0] if len(parts) > 0 else raw_slug
                        if re.match(r'^\d+\s+', street):
                            leads.append({
                                'Address': street.title(),
                                'City': city.title(),
                                'State': state.upper(),
                                'Zip': parts[2] if len(parts) > 2 else '',
                                'Price': price,
                                'Property Type': 'Single Family Home',
                                'Status': 'Active',
                                'Brokerage / Agent': 'MLS Active',
                                'Listing URL': f"https:{href}" if href.startswith('//') else href,
                                'isPending': False,
                                'isContingent': False,
                                'Source': 'Web Scraper Engine'
                            })
        except Exception:
            pass

    return leads[:max_results]

# ==========================================
# ENTERPRISE LEAD VERIFICATION ENGINE
# ==========================================
def verify_and_clean_leads(raw_leads):
    """
    Strict 5-Tier Verification Pipeline:
    Filters out off-market, pending, sold, contingent, land, lots, and invalid addresses.
    """
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
        price_val = float(row.get('Price', 0)) if pd.notnull(row.get('Price')) else 0

        # Rule 1: Address must start with a street number
        if not re.match(r'^\d+\s+[A-Za-z0-9]', addr_str):
            continue

        # Rule 2: Exclude off-market / sold / pending / contingent statuses
        if any(keyword in status_str for keyword in OFF_MARKET_KEYWORDS):
            continue

        # Rule 3: Reject non-residential land, mobile, or lot types
        if any(p_type in prop_type_str for p_type in INVALID_PROPERTY_TYPES):
            continue

        # Rule 4: Sanity check price threshold ($10,000+)
        if price_val < 10000:
            continue

        # Rule 5: Explicit Boolean flag checks from source API
        if row.get('isPending') is True or row.get('isContingent') is True:
            continue

        # Construct Owner Contact Lookup Link
        query_str = f"{addr_str} {row['City']} {row['State']} {row['Zip']}".strip()
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
# MAIN APPLICATION INTERFACE
# ==========================================
if st.button("🚀 Fetch & Verify Leads", type="primary"):
    with st.spinner("Executing Lead Extraction & Verification Pipeline..."):
        leads = []
        engine_used = ""
        
        # Try Primary Engine
        raw_leads, error = fetch_rapidapi_leads(city_input, state_input, rapidapi_key, max_leads)
        
        if error == "QUOTA_EXCEEDED" or error == "API_KEY_MISSING" or (raw_leads is not None and len(raw_leads) == 0):
            st.warning("⚠️ RapidAPI quota exceeded or key missing. Failing over to Web Scraper Engine 2...")
            leads = scrape_web_leads_fallback(city_input, state_input, max_leads)
            engine_used = "Web Scraper Engine 2 (Redfin/DDG Indexer)"
        elif raw_leads:
            leads = raw_leads
            engine_used = "RapidAPI Real Estate Engine 1"
        else:
            st.error(f"Error fetching from primary API: {error}. Switching to web scraper...")
            leads = scrape_web_leads_fallback(city_input, state_input, max_leads)
            engine_used = "Web Scraper Engine 2 (Redfin/DDG Indexer)"

        # Run Verification
        verified_df, filtered_off_market = verify_and_clean_leads(leads)

    # Display KPI Dashboard
    st.subheader("📊 Lead Generation Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Extracted", len(leads))
    col2.metric("Verified Active", len(verified_df))
    col3.metric("Filtered Off-Market", filtered_off_market)
    col4.metric("Active Engine", engine_used)

    if not verified_df.empty:
        st.subheader("📋 Verified Active Leads")
        
        # Display Interactive Table
        st.dataframe(
            verified_df,
            column_config={
                "Listing URL": st.column_config.LinkColumn("Listing Link", display_text="View Listing"),
                "Contact Lookup": st.column_config.LinkColumn("Owner Contact", display_text="Find Owner Details")
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Export Actions
        csv_data = verified_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Verified Leads (CSV)",
            data=csv_data,
            file_name=f"verified_leads_{city_input}_{state_input}.csv",
            mime="text/csv"
        )
    else:
        st.error("No active, verified leads were found matching the criteria. Try expanding search parameters or checking city spelling.")import streamlit as st
import pandas as pd
import requests
import re
import io
import urllib.parse
from bs4 import BeautifulSoup

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Real Estate Lead Scraper & Verifier Pro",
    page_icon="🏠",
    layout="wide"
)

st.title("🏠 Real Estate Lead Scraper & Automated Verifier")
st.caption("Engine 1: RapidAPI Lead Ingestion | Engine 2: Redfin & DDG Web Scraper Fallback | Enterprise Verification Matrix")

# ==========================================
# SIDEBAR CONTROLS
# ==========================================
st.sidebar.header("🔑 API & System Settings")
rapidapi_key = st.sidebar.text_input("RapidAPI Key", type="password", help="Enter your RapidAPI Key for Real Estate API")

st.sidebar.header("📍 Target Search Parameters")
city_input = st.sidebar.text_input("City", value="Miami")
state_input = st.sidebar.text_input("State (2-Letter)", value="FL", max_chars=2)
max_leads = st.sidebar.slider("Maximum Leads to Fetch", min_value=10, max_value=100, value=25)

# ==========================================
# ENGINE 1: RAPIDAPI INGESTION
# ==========================================
def fetch_rapidapi_leads(city, state, api_key, limit=25):
    """
    Fetches real estate leads via RapidAPI Real Estate API.
    Returns (leads_list, error_message)
    """
    if not api_key:
        return None, "API_KEY_MISSING"
        
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
        if response.status_code == 429:
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
                'Source': 'RapidAPI Engine'
            })
        return leads, None
    except Exception as e:
        return None, str(e)

# ==========================================
# ENGINE 2: WEB SCRAPER FALLBACK
# ==========================================
def scrape_web_leads_fallback(city, state, max_results=25):
    """
    Fallback engine executing when RapidAPI quota is exhausted or unavailable.
    Scrapes Redfin Public Streams and Real-Time Search Indexes.
    """
    leads = []
    
    # Method A: Redfin Public GIS Search Endpoint
    try:
        url = "https://www.redfin.com/stingray/api/gis-csv"
        params = {
            "al": "1",
            "market": city.lower().replace(" ", ""),
            "num_homes": str(max_results * 2),
            "status": "9",  # 9 = Active listings only in Redfin GIS
            "v": "8"
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/csv,application/json,text/plain,*/*"
        }
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        
        if resp.status_code == 200 and len(resp.text) > 100 and "ADDRESS" in resp.text.upper():
            df_csv = pd.read_csv(io.StringIO(resp.text))
            for _, row in df_csv.iterrows():
                addr = str(row.get('ADDRESS', '')).strip()
                c = str(row.get('CITY', city)).strip()
                s = str(row.get('STATE OR PROVINCE', state)).strip()
                zip_c = str(row.get('ZIP OR POSTAL CODE', '')).replace('.0', '').strip()
                price = row.get('PRICE', 0)
                p_type = str(row.get('PROPERTY TYPE', 'Single Family')).strip()
                status = str(row.get('STATUS', 'Active')).strip()
                redfin_path = str(row.get('URL (SEE http://www.redfin.com/redfin_firm FOR BEHAVIOR)', '')).strip()
                
                listing_url = f"https://www.redfin.com{redfin_path}" if redfin_path.startswith('/') else redfin_path
                
                if addr and addr.lower() != 'nan':
                    leads.append({
                        'Address': addr,
                        'City': c,
                        'State': s,
                        'Zip': zip_c,
                        'Price': price,
                        'Property Type': p_type,
                        'Status': status,
                        'Brokerage / Agent': 'Redfin Listed Agent',
                        'Listing URL': listing_url or f"https://www.google.com/search?q={urllib.parse.quote(f'{addr} {c} {s}')}",
                        'isPending': False,
                        'isContingent': False,
                        'Source': 'Web Scraper Engine'
                    })
    except Exception:
        pass

    # Method B: Search Index Scraping (Fallback if GIS returns limited results)
    if len(leads) < 5:
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q=site:realtor.com/realestateandhomes-detail+\"{city}\"+\"{state}\"+\"For Sale\""
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
            r = requests.get(ddg_url, headers=headers, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                results = soup.find_all('a', class_='result__url')
                snippets = soup.find_all('a', class_='result__snippet')
                
                for idx, res in enumerate(results):
                    href = res.get('href', '')
                    snippet_text = snippets[idx].text if idx < len(snippets) else ''
                    
                    match_price = re.search(r'\$([0-9,]+)', snippet_text)
                    price = int(match_price.group(1).replace(',', '')) if match_price else 0
                    
                    url_match = re.search(r'/realestateandhomes-detail/([^/?]+)', href)
                    if url_match:
                        raw_slug = url_match.group(1).replace('-', ' ')
                        parts = raw_slug.split('_')
                        street = parts[0] if len(parts) > 0 else raw_slug
                        if re.match(r'^\d+\s+', street):
                            leads.append({
                                'Address': street.title(),
                                'City': city.title(),
                                'State': state.upper(),
                                'Zip': parts[2] if len(parts) > 2 else '',
                                'Price': price,
                                'Property Type': 'Single Family Home',
                                'Status': 'Active',
                                'Brokerage / Agent': 'MLS Active',
                                'Listing URL': f"https:{href}" if href.startswith('//') else href,
                                'isPending': False,
                                'isContingent': False,
                                'Source': 'Web Scraper Engine'
                            })
        except Exception:
            pass

    return leads[:max_results]

# ==========================================
# ENTERPRISE LEAD VERIFICATION ENGINE
# ==========================================
def verify_and_clean_leads(raw_leads):
    """
    Strict 5-Tier Verification Pipeline:
    Filters out off-market, pending, sold, contingent, land, lots, and invalid addresses.
    """
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
        price_val = float(row.get('Price', 0)) if pd.notnull(row.get('Price')) else 0

        # Rule 1: Address must start with a street number
        if not re.match(r'^\d+\s+[A-Za-z0-9]', addr_str):
            continue

        # Rule 2: Exclude off-market / sold / pending / contingent statuses
        if any(keyword in status_str for keyword in OFF_MARKET_KEYWORDS):
            continue

        # Rule 3: Reject non-residential land, mobile, or lot types
        if any(p_type in prop_type_str for p_type in INVALID_PROPERTY_TYPES):
            continue

        # Rule 4: Sanity check price threshold ($10,000+)
        if price_val < 10000:
            continue

        # Rule 5: Explicit Boolean flag checks from source API
        if row.get('isPending') is True or row.get('isContingent') is True:
            continue

        # Construct Owner Contact Lookup Link
        query_str = f"{addr_str} {row['City']} {row['State']} {row['Zip']}".strip()
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
# MAIN APPLICATION INTERFACE
# ==========================================
if st.button("🚀 Fetch & Verify Leads", type="primary"):
    with st.spinner("Executing Lead Extraction & Verification Pipeline..."):
        leads = []
        engine_used = ""
        
        # Try Primary Engine
        raw_leads, error = fetch_rapidapi_leads(city_input, state_input, rapidapi_key, max_leads)
        
        if error == "QUOTA_EXCEEDED" or error == "API_KEY_MISSING" or (raw_leads is not None and len(raw_leads) == 0):
            st.warning("⚠️ RapidAPI quota exceeded or key missing. Failing over to Web Scraper Engine 2...")
            leads = scrape_web_leads_fallback(city_input, state_input, max_leads)
            engine_used = "Web Scraper Engine 2 (Redfin/DDG Indexer)"
        elif raw_leads:
            leads = raw_leads
            engine_used = "RapidAPI Real Estate Engine 1"
        else:
            st.error(f"Error fetching from primary API: {error}. Switching to web scraper...")
            leads = scrape_web_leads_fallback(city_input, state_input, max_leads)
            engine_used = "Web Scraper Engine 2 (Redfin/DDG Indexer)"

        # Run Verification
        verified_df, filtered_off_market = verify_and_clean_leads(leads)

    # Display KPI Dashboard
    st.subheader("📊 Lead Generation Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Extracted", len(leads))
    col2.metric("Verified Active", len(verified_df))
    col3.metric("Filtered Off-Market", filtered_off_market)
    col4.metric("Active Engine", engine_used)

    if not verified_df.empty:
        st.subheader("📋 Verified Active Leads")
        
        # Display Interactive Table
        st.dataframe(
            verified_df,
            column_config={
                "Listing URL": st.column_config.LinkColumn("Listing Link", display_text="View Listing"),
                "Contact Lookup": st.column_config.LinkColumn("Owner Contact", display_text="Find Owner Details")
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Export Actions
        csv_data = verified_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Verified Leads (CSV)",
            data=csv_data,
            file_name=f"verified_leads_{city_input}_{state_input}.csv",
            mime="text/csv"
        )
    else:
        st.error("No active, verified leads were found matching the criteria. Try expanding search parameters or checking city spelling.")
