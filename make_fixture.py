"""
make_fixture.py - writes data/fixtures/mock_open_ninja_leads.json

Run from your project root (the folder containing app.py):
    python make_fixture.py
"""
import json
import os
import random

OUT = os.path.join("data", "fixtures", "mock_open_ninja_leads.json")

# If your api.py unwraps a different nesting, change this wrapper to match it.
def wrap(properties):
    return {"status": "OK", "request_id": "mock-0001", "data": properties}


def build(n=45, seed=7):
    rnd = random.Random(seed)
    streets = ["Oak St", "Maple Ave", "Pine Rd", "Cedar Ln", "Elm Dr", "Lake Blvd"]
    zips = ["75201", "75202", "75203", "75204", "75205"]
    props = []
    for i in range(n):
        sqft = rnd.randint(800, 2800)
        ppsf = rnd.uniform(90, 210)
        price = int(sqft * ppsf / 1000) * 1000
        z = zips[i % len(zips)]
        props.append({
            "zpid": str(20000000 + i),
            "address": f"{rnd.randint(100, 9999)} {rnd.choice(streets)}",
            "city": "Dallas",
            "state": "TX",
            "zipcode": z,
            "price": price,
            "livingArea": sqft,
            "bedrooms": rnd.choice([2, 3, 3, 4, 5]),
            "bathrooms": rnd.choice([1, 2, 2, 3]),
            "homeStatus": "FOR_SALE",
            "priceReduction": rnd.choice([0, 0, 0, 5000, 10000, 15000, 25000]),
            "detailUrl": f"https://www.zillow.com/homedetails/{20000000 + i}_zpid/",
        })
    return props


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(wrap(build()), f, indent=2)
    print(f"Wrote {OUT}")
