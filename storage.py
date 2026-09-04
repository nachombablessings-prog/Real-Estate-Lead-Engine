import json
from pathlib import Path
from datetime import datetime

RAW_DIR = Path("data/raw")
FIXTURE_DIR = Path("data/fixtures")

def save_raw_response(data: dict, source: str, location: str) -> str:
    """Saves raw API response payload to disk before any processing."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = RAW_DIR / f"{source}_{location.lower().replace(' ', '_')}_{timestamp}.json"
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    return str(filename)

def load_fixture(fixture_name: str) -> dict:
    """Loads a local JSON fixture file for offline testing."""
    fixture_path = FIXTURE_DIR / fixture_name
    if not fixture_path.exists():
        # Fallback check in raw directory if fixture not found
        fixture_path = RAW_DIR / fixture_name
        
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture file not found at {fixture_path}")
        
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)
