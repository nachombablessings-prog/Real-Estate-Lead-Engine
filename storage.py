import json
import os
import time

DATA_DIR = "data/raw/"
FIXTURE_DIR = "data/fixtures/"

def save_raw_response(data, source, location):
    """Saves raw JSON API responses to the disk for auditing and backup."""
    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(DATA_DIR, f"{source}_{location}_{timestamp}.json")
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        
    return filepath

def load_fixture(filename):
    """Loads a local JSON file for offline test mode."""
    filepath = os.path.join(FIXTURE_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError(f"Fixture {filename} not found.")
