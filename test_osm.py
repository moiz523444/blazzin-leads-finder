import urllib.request
import urllib.parse
import json

cities = {
    "US_Dallas": (32.7767, -96.7970),
    "UK_Manchester": (53.4808, -2.2426),
    "CA_Toronto": (43.6532, -79.3832),
}

for name, (lat, lon) in cities.items():
    query = f'[out:json][timeout:10];nwr["phone"]["website"](around:15000, {lat}, {lon});out tags 10;'
    url = "https://overpass-api.de/api/interpreter?data=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": "BlazzinHarvester/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            elements = data.get("elements", [])
            print(f"=== {name}: {len(elements)} businesses found ===")
            for el in elements[:4]:
                tags = el.get("tags", {})
                print("  *", tags.get("name"), "|", tags.get("phone"), "|", tags.get("website"))
    except Exception as e:
        print(f"=== {name} error: {e} ===")
