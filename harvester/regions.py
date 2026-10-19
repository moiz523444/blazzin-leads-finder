"""
Every state / province / region / emirate / municipality of the 5 target markets,
each with its main business cities (name, lat, lon). Scans rotate through these so
leads come from the whole country, not one city.
"""
import random
from typing import Dict, List, Tuple

City = Tuple[str, float, float]

REGIONS: Dict[str, Dict[str, List[City]]] = {
    "US": {
        "Alabama": [("Birmingham", 33.52, -86.80), ("Montgomery", 32.37, -86.30), ("Huntsville", 34.73, -86.59), ("Mobile", 30.69, -88.04)],
        "Alaska": [("Anchorage", 61.22, -149.90), ("Fairbanks", 64.84, -147.72), ("Juneau", 58.30, -134.42)],
        "Arizona": [("Phoenix", 33.45, -112.07), ("Tucson", 32.22, -110.97), ("Scottsdale", 33.49, -111.93), ("Mesa", 33.42, -111.83)],
        "Arkansas": [("Little Rock", 34.75, -92.29), ("Fayetteville", 36.06, -94.16), ("Fort Smith", 35.39, -94.40)],
        "California": [("Los Angeles", 34.05, -118.24), ("San Diego", 32.72, -117.16), ("San Francisco", 37.77, -122.42), ("San Jose", 37.34, -121.89), ("Sacramento", 38.58, -121.49), ("Fresno", 36.74, -119.79), ("Irvine", 33.68, -117.83)],
        "Colorado": [("Denver", 39.74, -104.99), ("Colorado Springs", 38.83, -104.82), ("Boulder", 40.01, -105.27), ("Fort Collins", 40.59, -105.08)],
        "Connecticut": [("Hartford", 41.76, -72.68), ("New Haven", 41.31, -72.92), ("Stamford", 41.05, -73.54), ("Bridgeport", 41.19, -73.20)],
        "Delaware": [("Wilmington", 39.74, -75.55), ("Dover", 39.16, -75.52), ("Newark", 39.68, -75.75)],
        "District of Columbia": [("Washington", 38.91, -77.04)],
        "Florida": [("Miami", 25.76, -80.19), ("Orlando", 28.54, -81.38), ("Tampa", 27.95, -82.46), ("Jacksonville", 30.33, -81.66), ("Fort Lauderdale", 26.12, -80.14), ("Tallahassee", 30.44, -84.28)],
        "Georgia": [("Atlanta", 33.75, -84.39), ("Savannah", 32.08, -81.09), ("Augusta", 33.47, -81.97), ("Athens", 33.96, -83.38)],
        "Hawaii": [("Honolulu", 21.31, -157.86), ("Hilo", 19.71, -155.08), ("Kahului", 20.89, -156.47)],
        "Idaho": [("Boise", 43.62, -116.20), ("Idaho Falls", 43.49, -112.03), ("Coeur d'Alene", 47.68, -116.78)],
        "Illinois": [("Chicago", 41.88, -87.63), ("Springfield", 39.78, -89.65), ("Naperville", 41.75, -88.15), ("Peoria", 40.69, -89.59)],
        "Indiana": [("Indianapolis", 39.77, -86.16), ("Fort Wayne", 41.08, -85.14), ("Evansville", 37.97, -87.57), ("South Bend", 41.68, -86.25)],
        "Iowa": [("Des Moines", 41.59, -93.62), ("Cedar Rapids", 41.98, -91.67), ("Davenport", 41.52, -90.58)],
        "Kansas": [("Wichita", 37.69, -97.34), ("Overland Park", 38.98, -94.67), ("Kansas City", 39.11, -94.63), ("Topeka", 39.05, -95.68)],
        "Kentucky": [("Louisville", 38.25, -85.76), ("Lexington", 38.04, -84.50), ("Bowling Green", 36.99, -86.44)],
        "Louisiana": [("New Orleans", 29.95, -90.07), ("Baton Rouge", 30.45, -91.15), ("Shreveport", 32.53, -93.75), ("Lafayette", 30.22, -92.02)],
        "Maine": [("Portland", 43.66, -70.26), ("Bangor", 44.80, -68.77), ("Augusta", 44.31, -69.78)],
        "Maryland": [("Baltimore", 39.29, -76.61), ("Annapolis", 38.98, -76.49), ("Rockville", 39.08, -77.15), ("Frederick", 39.41, -77.41)],
        "Massachusetts": [("Boston", 42.36, -71.06), ("Worcester", 42.26, -71.80), ("Springfield", 42.10, -72.59), ("Cambridge", 42.37, -71.11)],
        "Michigan": [("Detroit", 42.33, -83.05), ("Grand Rapids", 42.96, -85.67), ("Lansing", 42.73, -84.56), ("Ann Arbor", 42.28, -83.74)],
        "Minnesota": [("Minneapolis", 44.98, -93.27), ("Saint Paul", 44.95, -93.09), ("Rochester", 44.02, -92.47), ("Duluth", 46.79, -92.10)],
        "Mississippi": [("Jackson", 32.30, -90.18), ("Gulfport", 30.37, -89.09), ("Hattiesburg", 31.33, -89.29)],
        "Missouri": [("Kansas City", 39.10, -94.58), ("St. Louis", 38.63, -90.20), ("Springfield", 37.21, -93.29), ("Columbia", 38.95, -92.33)],
        "Montana": [("Billings", 45.78, -108.50), ("Missoula", 46.87, -113.99), ("Bozeman", 45.68, -111.04), ("Helena", 46.59, -112.04)],
        "Nebraska": [("Omaha", 41.26, -95.93), ("Lincoln", 40.81, -96.70)],
        "Nevada": [("Las Vegas", 36.17, -115.14), ("Reno", 39.53, -119.81), ("Henderson", 36.04, -114.98)],
        "New Hampshire": [("Manchester", 42.99, -71.46), ("Nashua", 42.77, -71.47), ("Concord", 43.21, -71.54)],
        "New Jersey": [("Newark", 40.74, -74.17), ("Jersey City", 40.73, -74.08), ("Trenton", 40.22, -74.76), ("Princeton", 40.36, -74.67)],
        "New Mexico": [("Albuquerque", 35.08, -106.65), ("Santa Fe", 35.69, -105.94), ("Las Cruces", 32.32, -106.76)],
        "New York": [("New York City", 40.71, -74.01), ("Brooklyn", 40.68, -73.94), ("Buffalo", 42.89, -78.88), ("Rochester", 43.16, -77.61), ("Albany", 42.65, -73.76), ("Syracuse", 43.05, -76.15)],
        "North Carolina": [("Charlotte", 35.23, -80.84), ("Raleigh", 35.78, -78.64), ("Durham", 35.99, -78.90), ("Greensboro", 36.07, -79.79), ("Asheville", 35.60, -82.55)],
        "North Dakota": [("Fargo", 46.88, -96.79), ("Bismarck", 46.81, -100.78), ("Grand Forks", 47.93, -97.03)],
        "Ohio": [("Columbus", 39.96, -83.00), ("Cleveland", 41.50, -81.69), ("Cincinnati", 39.10, -84.51), ("Toledo", 41.65, -83.54), ("Akron", 41.08, -81.52)],
        "Oklahoma": [("Oklahoma City", 35.47, -97.52), ("Tulsa", 36.15, -95.99), ("Norman", 35.22, -97.44)],
        "Oregon": [("Portland", 45.52, -122.68), ("Salem", 44.94, -123.04), ("Eugene", 44.05, -123.09), ("Bend", 44.06, -121.32)],
        "Pennsylvania": [("Philadelphia", 39.95, -75.17), ("Pittsburgh", 40.44, -79.99), ("Harrisburg", 40.27, -76.88), ("Allentown", 40.61, -75.49)],
        "Rhode Island": [("Providence", 41.82, -71.41), ("Warwick", 41.70, -71.42), ("Newport", 41.49, -71.31)],
        "South Carolina": [("Charleston", 32.78, -79.93), ("Columbia", 34.00, -81.03), ("Greenville", 34.85, -82.40), ("Myrtle Beach", 33.69, -78.89)],
        "South Dakota": [("Sioux Falls", 43.54, -96.73), ("Rapid City", 44.08, -103.23), ("Pierre", 44.37, -100.35)],
        "Tennessee": [("Nashville", 36.16, -86.78), ("Memphis", 35.15, -90.05), ("Knoxville", 35.96, -83.92), ("Chattanooga", 35.05, -85.31)],
        "Texas": [("Houston", 29.76, -95.37), ("Dallas", 32.78, -96.80), ("Austin", 30.27, -97.74), ("San Antonio", 29.42, -98.49), ("Fort Worth", 32.76, -97.33), ("El Paso", 31.76, -106.49), ("Plano", 33.02, -96.70)],
        "Utah": [("Salt Lake City", 40.76, -111.89), ("Provo", 40.23, -111.66), ("Ogden", 41.22, -111.97), ("St. George", 37.10, -113.58)],
        "Vermont": [("Burlington", 44.48, -73.21), ("Montpelier", 44.26, -72.58), ("Rutland", 43.61, -72.97)],
        "Virginia": [("Virginia Beach", 36.85, -75.98), ("Richmond", 37.54, -77.44), ("Arlington", 38.88, -77.10), ("Norfolk", 36.85, -76.29), ("Roanoke", 37.27, -79.94)],
        "Washington": [("Seattle", 47.61, -122.33), ("Spokane", 47.66, -117.43), ("Tacoma", 47.25, -122.44), ("Bellevue", 47.61, -122.20)],
        "West Virginia": [("Charleston", 38.35, -81.63), ("Huntington", 38.42, -82.45), ("Morgantown", 39.63, -79.96)],
        "Wisconsin": [("Milwaukee", 43.04, -87.91), ("Madison", 43.07, -89.40), ("Green Bay", 44.52, -88.02)],
        "Wyoming": [("Cheyenne", 41.14, -104.82), ("Casper", 42.87, -106.31), ("Jackson", 43.48, -110.76)],
    },
    "CA": {
        "Ontario": [("Toronto", 43.65, -79.38), ("Ottawa", 45.42, -75.70), ("Mississauga", 43.59, -79.64), ("Hamilton", 43.26, -79.87), ("London", 42.98, -81.25), ("Kitchener", 43.45, -80.49)],
        "Quebec": [("Montreal", 45.50, -73.57), ("Quebec City", 46.81, -71.21), ("Laval", 45.61, -73.71), ("Gatineau", 45.48, -75.70)],
        "British Columbia": [("Vancouver", 49.28, -123.12), ("Surrey", 49.19, -122.85), ("Victoria", 48.43, -123.37), ("Kelowna", 49.89, -119.50)],
        "Alberta": [("Calgary", 51.05, -114.07), ("Edmonton", 53.55, -113.49), ("Red Deer", 52.27, -113.81)],
        "Manitoba": [("Winnipeg", 49.90, -97.14), ("Brandon", 49.85, -99.95)],
        "Saskatchewan": [("Saskatoon", 52.13, -106.67), ("Regina", 50.45, -104.61)],
        "Nova Scotia": [("Halifax", 44.65, -63.58), ("Sydney", 46.14, -60.19)],
        "New Brunswick": [("Moncton", 46.09, -64.78), ("Saint John", 45.27, -66.06), ("Fredericton", 45.96, -66.64)],
        "Newfoundland and Labrador": [("St. John's", 47.56, -52.71), ("Corner Brook", 48.95, -57.95)],
        "Prince Edward Island": [("Charlottetown", 46.24, -63.13), ("Summerside", 46.39, -63.79)],
        "Northwest Territories": [("Yellowknife", 62.45, -114.37)],
        "Yukon": [("Whitehorse", 60.72, -135.06)],
        "Nunavut": [("Iqaluit", 63.75, -68.52)],
    },
    "UK": {
        "London": [("Central London", 51.51, -0.13), ("Croydon", 51.37, -0.10), ("Wembley", 51.55, -0.30), ("Stratford", 51.54, -0.003)],
        "South East England": [("Brighton", 50.82, -0.14), ("Reading", 51.45, -0.97), ("Oxford", 51.75, -1.26), ("Southampton", 50.91, -1.40), ("Milton Keynes", 52.04, -0.76), ("Canterbury", 51.28, 1.08)],
        "South West England": [("Bristol", 51.45, -2.59), ("Plymouth", 50.38, -4.14), ("Exeter", 50.72, -3.53), ("Bournemouth", 50.72, -1.88), ("Bath", 51.38, -2.36)],
        "East of England": [("Cambridge", 52.21, 0.12), ("Norwich", 52.63, 1.30), ("Ipswich", 52.06, 1.16), ("Chelmsford", 51.74, 0.47), ("Luton", 51.88, -0.42)],
        "West Midlands": [("Birmingham", 52.49, -1.89), ("Coventry", 52.41, -1.51), ("Wolverhampton", 52.59, -2.13), ("Stoke-on-Trent", 53.00, -2.18)],
        "East Midlands": [("Nottingham", 52.95, -1.15), ("Leicester", 52.64, -1.13), ("Derby", 52.92, -1.48), ("Northampton", 52.24, -0.90), ("Lincoln", 53.23, -0.54)],
        "North West England": [("Manchester", 53.48, -2.24), ("Liverpool", 53.41, -2.98), ("Preston", 53.76, -2.70), ("Bolton", 53.58, -2.43), ("Chester", 53.19, -2.89)],
        "Yorkshire and the Humber": [("Leeds", 53.80, -1.55), ("Sheffield", 53.38, -1.47), ("Bradford", 53.80, -1.75), ("York", 53.96, -1.08), ("Hull", 53.74, -0.33)],
        "North East England": [("Newcastle upon Tyne", 54.98, -1.62), ("Sunderland", 54.91, -1.38), ("Middlesbrough", 54.57, -1.23), ("Durham", 54.78, -1.57)],
        "Scotland": [("Glasgow", 55.86, -4.25), ("Edinburgh", 55.95, -3.19), ("Aberdeen", 57.15, -2.09), ("Dundee", 56.46, -2.97), ("Inverness", 57.48, -4.22)],
        "Wales": [("Cardiff", 51.48, -3.18), ("Swansea", 51.62, -3.94), ("Newport", 51.58, -2.99), ("Wrexham", 53.05, -3.00)],
        "Northern Ireland": [("Belfast", 54.60, -5.93), ("Derry", 54.99, -7.32), ("Lisburn", 54.51, -6.04)],
    },
    "UAE": {
        "Dubai": [("Downtown Dubai", 25.20, 55.27), ("Deira", 25.27, 55.31), ("Jumeirah", 25.21, 55.25), ("Dubai Marina", 25.08, 55.14), ("Al Barsha", 25.11, 55.20)],
        "Abu Dhabi": [("Abu Dhabi City", 24.45, 54.38), ("Al Ain", 24.21, 55.74), ("Khalifa City", 24.42, 54.58)],
        "Sharjah": [("Sharjah City", 25.35, 55.42), ("Khor Fakkan", 25.34, 56.35)],
        "Ajman": [("Ajman", 25.41, 55.51)],
        "Umm Al Quwain": [("Umm Al Quwain", 25.56, 55.55)],
        "Ras Al Khaimah": [("Ras Al Khaimah", 25.79, 55.94)],
        "Fujairah": [("Fujairah", 25.13, 56.33), ("Dibba", 25.62, 56.27)],
    },
    "QA": {
        "Doha": [("Doha", 25.29, 51.53), ("West Bay", 25.32, 51.53), ("Al Sadd", 25.28, 51.50)],
        "Al Rayyan": [("Al Rayyan", 25.29, 51.42), ("Education City", 25.31, 51.44)],
        "Al Wakrah": [("Al Wakrah", 25.17, 51.60)],
        "Al Daayen": [("Lusail", 25.42, 51.49)],
        "Al Khor": [("Al Khor", 25.68, 51.50)],
        "Umm Salal": [("Umm Salal", 25.41, 51.40)],
        "Al Shamal": [("Madinat ash Shamal", 26.13, 51.20)],
        "Al Shahaniya": [("Al Shahaniya", 25.37, 51.20)],
    },
}

COUNTRY_NAMES = {"US": "United States", "UK": "United Kingdom", "CA": "Canada", "UAE": "United Arab Emirates", "QA": "Qatar"}
# ISO 3166-1 alpha-2 codes used by map APIs and phonenumbers
ISO2 = {"US": "US", "UK": "GB", "CA": "CA", "UAE": "AE", "QA": "QA"}


def list_regions() -> Dict[str, List[str]]:
    return {c: sorted(r.keys()) for c, r in REGIONS.items()}


def pick_targets(country: str, region: str = "all", count: int = 6) -> List[Tuple[str, str, City]]:
    """
    Returns up to `count` (country, region, city) targets.
    - country 'ALL' spreads picks across all 5 countries
    - region 'all' rotates through random states/provinces, so repeated scans cover the whole country
    """
    country = (country or "ALL").upper()
    countries = list(REGIONS.keys()) if country == "ALL" else [country]
    countries = [c for c in countries if c in REGIONS]
    if not countries:
        return []

    if region and region.lower() != "all" and len(countries) == 1 and region in REGIONS[countries[0]]:
        cities = list(REGIONS[countries[0]][region])
        random.shuffle(cities)
        return [(countries[0], region, c) for c in cities[:count]]

    pool = [(c, r) for c in countries for r in REGIONS[c]]
    random.shuffle(pool)
    if country == "ALL":
        # Round-robin across countries so small markets (QA, UAE) are not drowned out by 51 US states
        by_country = {c: [p for p in pool if p[0] == c] for c in countries}
        random.shuffle(countries)
        ordered = []
        while any(by_country.values()):
            for c in countries:
                if by_country[c]:
                    ordered.append(by_country[c].pop())
        pool = ordered
    return [(c, r, random.choice(REGIONS[c][r])) for c, r in pool[:count]]
