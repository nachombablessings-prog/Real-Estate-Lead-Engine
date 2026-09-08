import streamlit as st
import pandas as pd

def render_metrics_banner(listings, crawl_depth):
    """Calculates and renders the top metrics row."""
    total_leads = len(listings)
    pipeline_value = sum(
        float(item.get('price', 0)) 
        for item in listings 
        if isinstance(item.get('price'), (int, float, str)) and str(item.get('price', 0)).replace('.','',1).isdigit()
    )
    avg_value = int(pipeline_value / total_leads) if total_leads > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Verified Leads", f"{total_leads:,}")
    m2.metric("Pipeline Value", f"${pipeline_value:,.0f}")
    m3.metric("Average Value", f"${avg_value:,.0f}")
    m4.metric("Engine Pages", crawl_depth)
    st.markdown("---")

def render_property_blocks(listings, df):
    """Renders the dual-view UI tabs (Cards vs Table)."""
    tab_block, tab_table = st.tabs(["🏠 Property Block View", "📊 Master Data Table"])

    with tab_block:
        st.download_button(
            "📥 Export These Leads to CSV", 
            df.to_csv(index=False).encode('utf-8'), 
            "leads_export.csv", 
            "text/csv"
        )
        st.markdown("---")
        
        for i in range(0, len(listings), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(listings):
                    item = listings[i + j]
                    price_val = str(item.get('price', 0)).replace('.','',1)
                    price_str = f"${int(item.get('price', 0)):,}" if price_val.isdigit() else str(item.get('price', 'N/A'))
                    
                    with cols[j]:
                        with st.container(border=True):
                            st.markdown(f"### {price_str}")
                            st.markdown(f"📍 **Address:** {item.get('address', 'Unavailable')}  \n"
                                        f"🏠 **Type:** {item.get('property_type', 'SINGLE_FAMILY')}  \n"
                                        f"🏢 **Broker:** {item.get('broker', item.get('listing_agent', 'Exclusive Agent'))}")
                            
                            b1, b2 = st.columns(2)
                            b1.button("🟢 Listing", key=f"list_{i}_{j}")
                            b2.button("🔍 Contact", key=f"cont_{i}_{j}")

    with tab_table:
        st.subheader("Master Database Table")
        st.dataframe(df, use_container_width=True)
