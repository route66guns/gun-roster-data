
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

# DOJ Recently Added Handgun Models URL
url = "https://oag.ca.gov/firearms/certified-handguns/recent"

# Request the page
response = requests.get(url)
soup = BeautifulSoup(response.content, "html.parser")

# Find the table of handgun models
table = soup.find("table")
rows = table.find_all("tr")[1:]  # skip header

handguns = []
for row in rows:
    cols = row.find_all("td")
    if len(cols) >= 5:
        manufacturer = cols[0].get_text(strip=True)
        model = cols[1].get_text(strip=True)
        caliber = cols[2].get_text(strip=True)
        gun_type = cols[3].get_text(strip=True)
        barrel_length = cols[4].get_text(strip=True)
        date_added = cols[5].get_text(strip=True) if len(cols) > 5 else None

        description = f"The {manufacturer} {model} is a recently certified handgun featuring a {barrel_length} barrel and chambered in {caliber}."
        features = [
            f"Caliber: {caliber}",
            f"Type: {gun_type}",
            f"Barrel Length: {barrel_length}",
            f"Manufacturer: {manufacturer}"
        ]

        handgun = {
            "manufacturer": manufacturer,
            "model": model,
            "caliber": caliber,
            "type": gun_type,
            "barrel_length": barrel_length,
            "date_added": date_added,
            "description": description,
            "features": features,
            "image_url": "https://via.placeholder.com/150x100?text=" + model.replace(" ", "+")
        }

        handguns.append(handgun)

# Output to JSON file
data = {
    "updated": datetime.now().isoformat(),
    "handguns": handguns
}

with open("sample_handguns.json", "w") as f:
    json.dump(data, f, indent=2)
