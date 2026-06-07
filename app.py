import os
import json
import math
import time
import re
import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from flask import Flask, render_template, request

app = Flask(__name__)

# Verify if the Google Maps API Key environment variable is detected at startup
print(f"GOOGLE_MAPS_API_KEY detected in env: {bool(os.environ.get('GOOGLE_MAPS_API_KEY'))}", flush=True)

# ── Paths ────────────────────────────────────────────────────────────────────
DATA_DIR   = os.path.join(os.path.dirname(__file__), "data")
FRASER_CSV = os.path.join(DATA_DIR, "fraser_schools.csv")
TTC_JSON   = os.path.join(DATA_DIR, "ttc_subway_stations.json")
GO_JSON    = os.path.join(DATA_DIR, "go_stations.json")

# ── Constants ────────────────────────────────────────────────────────────────
NOMINATIM_URL  = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter"
]
HEADERS        = {"User-Agent": "TorontoListingAnalyzer/1.0 (yash@kalani.name)"}
SCHOOL_RADIUS_M = 3000
WALK_SPEED_KMH  = 3.0
MAX_SCHOOLS     = 8


# ── Data loading (done once at startup) ──────────────────────────────────────
def _load_stations():
    with open(TTC_JSON) as f:
        ttc = json.load(f)
    with open(GO_JSON) as f:
        go = json.load(f)
    for s in ttc:
        s["network"] = "TTC Subway"
    for s in go:
        s["network"] = "GO Train"
    return ttc + go

def _load_fraser():
    if not os.path.exists(FRASER_CSV):
        return None
    return pd.read_csv(FRASER_CSV)

ONTARIO_SCHOOLS_TXT = os.path.join(DATA_DIR, "public_school_contact_list.txt")

def _load_ontario_schools():
    if not os.path.exists(ONTARIO_SCHOOLS_TXT):
        print("Downloading Ontario public school contact list...", flush=True)
        url = 'https://data.ontario.ca/dataset/fb3a7c18-90af-453e-bc0a-a76ecc471862/resource/f3a8c2a3-09d9-4715-9044-d8a0189f572c/download/public_school_contact_list__may2026_en.txt'
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            with open(ONTARIO_SCHOOLS_TXT, "w", encoding="utf-8") as f:
                f.write(r.text)
        except Exception as e:
            print(f"Error downloading contact list: {e}", flush=True)
            return []
            
    try:
        df = pd.read_csv(ONTARIO_SCHOOLS_TXT, sep="|")
        df = df[['School Name', 'Grade Range', 'School Type', 'Board Type', 'School Language']].dropna(subset=['School Name', 'Grade Range'])
        return df.to_dict(orient="records")
    except Exception as e:
        print(f"Error loading contact list: {e}", flush=True)
        return []

STATIONS  = _load_stations()
FRASER_DF = _load_fraser()
ONTARIO_SCHOOLS = _load_ontario_schools()


# ── Geo helpers ───────────────────────────────────────────────────────────────
def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))

def walk_minutes(dist_km):
    return round(dist_km / WALK_SPEED_KMH * 60)

def nearest_station(lat, lng):
    best = min(STATIONS, key=lambda s: haversine_km(lat, lng, s["lat"], s["lng"]))
    dist = haversine_km(lat, lng, best["lat"], best["lng"])
    return best, dist

def nearest_station_by_network(lat, lng, network):
    filtered = [s for s in STATIONS if s["network"] == network]
    if not filtered:
        return None, 0.0
    best = min(filtered, key=lambda s: haversine_km(lat, lng, s["lat"], s["lng"]))
    dist = haversine_km(lat, lng, best["lat"], best["lng"])
    return best, dist


def geocode(address, api_key=None):
    # Tier 1: Google Maps Geocoding API if key is available
    if not api_key:
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if api_key:
        try:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {"address": address, "key": api_key}
            r = requests.get(url, params=params, timeout=10)
            res = r.json()
            status = res.get("status")
            if status == "OK" and res.get("results"):
                loc = res["results"][0]["geometry"]["location"]
                return float(loc["lat"]), float(loc["lng"])
            else:
                print(f"Google Geocoding API returned status: {status}", flush=True)
                if "error_message" in res:
                    print(f"Error Message: {res['error_message']}", flush=True)
        except Exception as e:
            print(f"Google Geocoding failed: {e}", flush=True)
    else:
        print("Google Geocoding: Skipped (no GOOGLE_MAPS_API_KEY environment variable set)", flush=True)

    # Tier 2: OpenStreetMap Nominatim
    try:
        params = {"q": address, "format": "json", "limit": 1, "countrycodes": "ca"}
        r = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=10)
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"Nominatim Geocoding failed: {e}")

    # Tier 3: ArcGIS World Geocoding (especially useful for new street addresses missing in OSM)
    try:
        url = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
        params = {"f": "json", "singleLine": address, "maxLocations": 1}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data and data.get("candidates"):
            loc = data["candidates"][0]["location"]
            return float(loc["y"]), float(loc["x"])
    except Exception as e:
        print(f"ArcGIS Geocoding failed: {e}", flush=True)

    return None, None

def google_transit_directions(origin_lat, origin_lng, api_key=None):
    if not api_key:
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("Google Transit Directions: Skipped (no GOOGLE_MAPS_API_KEY environment variable set)", flush=True)
        return None

    # Calculate next weekday at 8:00 AM America/Toronto time
    tz = ZoneInfo("America/Toronto")
    now_tz = datetime.datetime.now(tz)
    proposed = now_tz + datetime.timedelta(days=(1 if now_tz.hour >= 8 else 0))
    days = (1 if now_tz.hour >= 8 else 0) + (2 if proposed.weekday() == 5 else 1 if proposed.weekday() == 6 else 0)
    target_dt = datetime.datetime.combine((now_tz + datetime.timedelta(days=days)).date(), datetime.time(8, 0, 0), tzinfo=tz)
    dep_time = int(target_dt.timestamp())

    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{origin_lat},{origin_lng}",
        "destination": "43.6453,-79.3806",  # Union Station
        "mode": "transit",
        "transit_mode": "train|subway",
        "key": api_key,
        "departure_time": str(dep_time)
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        status = data.get("status")
        if status == "OK" and data.get("routes"):
            route = data["routes"][0]
            leg = route["legs"][0]
            
            duration_min = round(leg["duration"]["value"] / 60)
            
            steps = leg["steps"]
            transit_lines = []
            parsed_steps = []
            
            for step in steps:
                travel_mode = step.get("travel_mode")
                step_duration = round(step["duration"]["value"] / 60)
                if step_duration == 0 and step["duration"]["value"] > 0:
                    step_duration = 1
                
                if travel_mode == "WALKING":
                    instructions = step.get("html_instructions", "Walk")
                    instructions = re.sub('<[^<]+?>', '', instructions)  # strip HTML tags
                    parsed_steps.append({
                        "type": "walk",
                        "description": instructions,
                        "duration": step_duration
                    })
                elif travel_mode == "TRANSIT":
                    details = step.get("transit_details", {})
                    line_info = details.get("line", {})
                    line_name = line_info.get("short_name") or line_info.get("name")
                    vehicle_type = line_info.get("vehicle", {}).get("type", "")
                    
                    vehicle_label = "Subway" if vehicle_type == "SUBWAY" else "Bus" if vehicle_type == "BUS" else "GO Train" if vehicle_type == "HEAVY_RAIL" else vehicle_type.lower().capitalize()
                    
                    departure_stop = details.get("departure_stop", {}).get("name", "Unknown Stop")
                    arrival_stop = details.get("arrival_stop", {}).get("name", "Unknown Stop")
                    num_stops = details.get("num_stops", 0)
                    
                    transit_lines.append(f"{line_name} ({vehicle_label})")
                    parsed_steps.append({
                        "type": "transit",
                        "line": line_name,
                        "vehicle": vehicle_label,
                        "departure": departure_stop,
                        "arrival": arrival_stop,
                        "stops": num_stops,
                        "duration": step_duration
                    })
                    
            route_summary = " ➔ ".join(transit_lines) if transit_lines else "Walk only"
            
            return {
                "duration_min": duration_min,
                "route_summary": route_summary,
                "steps": parsed_steps,
                "distance": leg.get("distance", {}).get("text", "")
            }
        else:
            print(f"Google Transit Directions API returned status: {status}", flush=True)
            if "error_message" in data:
                print(f"Error Message: {data['error_message']}", flush=True)
    except Exception as e:
        print(f"Google Transit Directions API failed: {e}", flush=True)
    return None

def overpass_schools(lat, lng, radius_m=SCHOOL_RADIUS_M):
    query = f"""
[out:json][timeout:25];
(
  node["amenity"="school"](around:{radius_m},{lat},{lng});
  way["amenity"="school"](around:{radius_m},{lat},{lng});
);
out center;
"""
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            r = requests.post(endpoint, data={"data": query}, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                data = r.json()
                schools = []
                for el in data.get("elements", []):
                    name = el.get("tags", {}).get("name", "")
                    if not name:
                        continue
                    slat = el.get("lat") or el.get("center", {}).get("lat")
                    slng = el.get("lon") or el.get("center", {}).get("lon")
                    if slat and slng:
                        schools.append({"name": name, "lat": float(slat), "lng": float(slng)})
                return schools
            else:
                print(f"Overpass endpoint {endpoint} returned status {r.status_code}")
        except Exception as e:
            print(f"Overpass endpoint {endpoint} failed: {e}")
            
    return []


# ── Fraser matching ───────────────────────────────────────────────────────────
STOPWORDS = {"school","public","catholic","elementary","separate","community",
             "junior","senior","the","of","and","la","de"}

def name_score(a, b):
    wa = set(a.lower().split()) - STOPWORDS
    wb = set(b.lower().split()) - STOPWORDS
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))

def find_school_details(osm_name):
    best_score = 0.0
    best_row = None
    
    for row in ONTARIO_SCHOOLS:
        school_name = str(row.get("School Name", ""))
        score = name_score(osm_name, school_name)
        if score > best_score:
            best_score = score
            best_row = row
            
    if best_score >= 0.4 and best_row is not None:
        school_type = str(best_row.get("School Type", ""))
        board_type = str(best_row.get("Board Type", ""))
        school_lang = str(best_row.get("School Language", ""))
        school_name = str(best_row.get("School Name", ""))
        
        is_public = (school_type == "Public") and ("Pub" in board_type)
        
        name_lower = school_name.lower()
        is_french_immersion = (school_lang == "French") or \
                              ("immersion" in name_lower) or \
                              ("français" in name_lower) or \
                              ("francais" in name_lower)
                              
        return best_row.get("Grade Range", "JK-8"), is_public, is_french_immersion

    # Fallback parsing on OSM school name if not matched in contact list
    name_lower = osm_name.lower()
    is_pub = ("catholic" not in name_lower) and \
             ("separate" not in name_lower) and \
             ("académie" not in name_lower) and \
             ("academie" not in name_lower) and \
             ("collège" not in name_lower) and \
             ("college" not in name_lower)
             
    is_french = ("immersion" in name_lower) or \
                ("français" in name_lower) or \
                ("francais" in name_lower) or \
                ("french" in name_lower)
                
    return "JK-8", is_pub, is_french

def covers_5_to_8(grade_range):
    if not isinstance(grade_range, str) or '-' not in grade_range:
        return False
    parts = grade_range.split('-')
    start_str, end_str = parts[0].strip(), parts[1].strip()
    
    if start_str in ['JK', 'K', 'SK']:
        start_val = 0
    else:
        try:
            start_val = int(start_str)
        except ValueError:
            return False
            
    try:
        end_val = int(end_str)
    except ValueError:
        return False
        
    return start_val <= 5 and end_val >= 8

def match_fraser(osm_schools, house_lat, house_lng):
    results = []
    for s in osm_schools:
        best_score, best_rating = 0.0, None
        if FRASER_DF is not None:
            for _, row in FRASER_DF.iterrows():
                sc = name_score(s["name"], str(row.get("name", "")))
                if sc > best_score:
                    best_score = sc
                    best_rating = row.get("rating")
                    
        dist = haversine_km(house_lat, house_lng, s["lat"], s["lng"])
        rating = float(best_rating) if best_score >= 0.3 and best_rating is not None and not pd.isna(best_rating) else None
        
        grade_range, is_public, is_french_immersion = find_school_details(s["name"])
        
        results.append({
            "school": s["name"],
            "rating": rating,
            "dist_km": round(dist, 2),
            "grade_range": grade_range,
            "is_public": is_public,
            "is_french_immersion": is_french_immersion
        })

    return sorted(results, key=lambda x: x["dist_km"])


def sort_by_rating(schools_list):
    # Sorts with rated schools first (highest rating to lowest),
    # and unrated schools last (sorted by distance).
    rated = sorted([s for s in schools_list if s["rating"] is not None], key=lambda x: -x["rating"])
    unrated = sorted([s for s in schools_list if s["rating"] is None], key=lambda x: x["dist_km"])
    return rated + unrated


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error  = None
    address = ""

    if request.method == "POST":
        address = request.form.get("address", "").strip()
        if address:
            try:
                lat, lng = geocode(address)
                time.sleep(1)  # Nominatim rate limit

                if lat is None:
                    error = "Address not found. Try adding the city and province, e.g. '123 Main St, Toronto, ON'."
                else:
                    # Google transit directions (door-to-door, handles multi-leg / transfer routes)
                    google_route = google_transit_directions(lat, lng)

                    osm_schools = overpass_schools(lat, lng)
                    schools_all = match_fraser(osm_schools, lat, lng)
                    
                    # Section 2: Best Schools Nearby (sorted by rating)
                    schools = sort_by_rating(schools_all)[:8]
                    
                    # Section 3: Public Schools (5-8 Span) Nearby (sorted by rating)
                    # Filter: Must be public, must cover 5-8 span, must not be French Immersion
                    schools_middle_all = [
                        s for s in schools_all 
                        if covers_5_to_8(s["grade_range"]) and s["is_public"] and not s["is_french_immersion"]
                    ]
                    schools_middle = sort_by_rating(schools_middle_all)[:8]

                    result = {
                        "address": address,
                        "google_route": google_route,
                        "schools": schools,
                        "schools_middle": schools_middle,
                        "fraser_loaded": FRASER_DF is not None,
                    }
            except Exception as e:
                error = f"Error: {e}"

    return render_template("index.html", result=result, error=error, address=address,
                           fraser_loaded=FRASER_DF is not None)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
