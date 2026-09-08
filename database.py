import sqlite3
import os

DB_PATH = "data/leads_master.db"

def initialize_database():
    """Creates the SQLite database and leads table if they do not exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verified_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT,
            price REAL,
            bedrooms INTEGER,
            bathrooms INTEGER,
            property_type TEXT,
            broker TEXT,
            source_api TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def log_leads_to_db(listings, source="Unknown"):
    """Inserts a batch of scraped listings into the local database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for item in listings:
        cursor.execute('''
            INSERT INTO verified_leads (address, price, bedrooms, bathrooms, property_type, broker, source_api)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            item.get("address", "N/A"),
            item.get("price", 0.0),
            item.get("bedrooms", 0),
            item.get("bathrooms", 0),
            item.get("property_type", "Unknown"),
            item.get("broker", item.get("listing_agent", "Unknown")),
            source
        ))
        
    conn.commit()
    conn.close()
