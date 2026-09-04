import sqlite3
import os
from pathlib import Path

DB_PATH = Path("data/leads.db")

def get_db_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Lead storage schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            zip TEXT,
            price REAL,
            property_type TEXT,
            status TEXT DEFAULT 'DISCOVERED',
            agent_name TEXT,
            broker_name TEXT,
            listing_url TEXT UNIQUE,
            source TEXT,
            verification_score INTEGER DEFAULT 0,
            verification_reason TEXT,
            first_seen TEXT,
            last_checked TEXT
        )
    """)
    
    # Search cache table (Priority 4)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_cache (
            search_key TEXT PRIMARY KEY,
            params_json TEXT,
            timestamp TEXT
        )
    """)
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    initialize_database()
    print("✅ Database initialized successfully at data/leads.db")
