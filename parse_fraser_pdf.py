"""
Parse the Fraser Institute PDF directly into data/fraser_schools.csv using a robust
visitor-based two-column cropping and grouping algorithm.
Run: py parse_fraser_pdf.py
"""

import re
import csv
import os
import pandas as pd
from pypdf import PdfReader

PDF_PATH = os.path.join(os.path.dirname(__file__), "data", "ontario-elementary-school-rankings-2025.pdf")
OUTPUT   = os.path.join(os.path.dirname(__file__), "data", "fraser_schools.csv")

# Build known cities list for splitting school name and city
def load_known_cities():
    known_cities = set()
    
    # Try reading from filtered_ontario_schools.csv in parent folder
    csv_path = os.path.join(os.path.dirname(__file__), "filtered_ontario_schools.csv")
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            if "City" in df.columns:
                for c in df["City"].dropna().unique():
                    norm = re.sub(r"[^a-z0-9]", "", str(c).lower())
                    if norm:
                        known_cities.add(norm)
        except Exception as e:
            print(f"Warning: could not load cities from CSV: {e}")
            
    # Also add standard large cities in Ontario manually just in case
    extra_cities = [
        "Toronto", "Ottawa", "Mississauga", "Brampton", "Hamilton", "London", 
        "Markham", "Vaughan", "Kitchener", "Windsor", "Richmond Hill", "Oakville", 
        "Burlington", "Greater Sudbury", "Sudbury", "Oshawa", "Barrie", "St. Catharines", 
        "Cambridge", "Kingston", "Guelph", "Thunder Bay", "Waterloo", "Brantford", 
        "Pickering", "Niagara Falls", "Peterborough", "Sarnia", "Sault Ste. Marie", 
        "Sault Ste Marie", "North York", "Scarborough", "Etobicoke", "East York", 
        "York", "Unionville", "Woodbridge", "Thornhill", "Maple", "St. Davids", "St Davids"
    ]
    for c in extra_cities:
        norm = re.sub(r"[^a-z0-9]", "", c.lower())
        known_cities.add(norm)
        
    return known_cities

def clean_spacing(text):
    # 1. Merge uppercase single letter with following word: "N orth" -> "North"
    text = re.sub(r"\b([A-Z])\s+([a-zA-Z])", r"\1\2", text)
    # 2. Merge common word endings that get split by PDF layout
    suffixes = ["th", "on", "a", "at", "ville", "tyr", "field", "wood", "land", "crest", "mount", "port", "bridge", "borough", "view", "halsa", "ar", "wa"]
    for suffix in suffixes:
        text = re.compile(r"\b([a-zA-Z]+)\s+(" + suffix + r")\b", re.IGNORECASE).sub(r"\1\2", text)
    # 3. Specific manual fixes for common PDF artifacts
    replacements = {
        "AI-Manar at": "AI-Manarat",
        "A l-Ameen": "Al-Ameen",
        "A l-Sadeq": "Al-Sadeq",
        "A lfajrul": "Alfajrul",
        "High P ark": "High Park",
        "K halsa": "Khalsa",
        "Niagar a": "Niagara",
        "Ir oquois": "Iroquois",
        "Nor th": "North",
        "Hamilt on": "Hamilton",
        "Union ville": "Unionville",
        "Mar wa": "Marwa",
        "S carborough": "Scarborough",
        "M ississauga": "Mississauga",
        "B rampton": "Brampton",
        "T oronto": "Toronto",
        "O akville": "Oakville",
        "H amilton": "Hamilton",
        "C ambridge": "Cambridge",
        "K ingston": "Kingston",
        "G uelph": "Guelph",
        "W aterloo": "Waterloo",
        "B rantford": "Brantford",
        "P ickering": "Pickering",
        "P eterborough": "Peterborough",
        "S arnia": "Sarnia",
        "S ault": "Sault",
        "V aughan": "Vaughan",
        "O shawa": "Oshawa",
        "B arrie": "Barrie",
        "E tobicoke": "Etobicoke",
        "E ast": "East",
        "Y ork": "York",
        "U nionville": "Unionville",
        "W oodbridge": "Woodbridge",
        "T hornhill": "Thornhill",
        "M aple": "Maple"
    }
    for k, v in replacements.items():
        text = re.sub(re.escape(k), v, text, flags=re.IGNORECASE)
    
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def parse_record_line(line, known_cities):
    # Skip lines containing typical header/footer words
    if any(h in line for h in ["School name", "Overall rating", "Last", "Trend", "City", "yrs", "Report Card", "Studies in Education"]):
        return None
        
    tokens = line.strip().split()
    if len(tokens) < 5:
        return None
        
    # Check if first token is a rank
    if not (tokens[0].isdigit() or tokens[0] == "n/a"):
        return None
        
    rank_2024 = tokens[0]
    
    # Parse rank_5yr and trend
    idx = 1
    rank_5yr = "n/a"
    trend = "—"
    
    if tokens[idx].isdigit() or tokens[idx] == "n/a":
        rank_5yr = tokens[idx]
        idx += 1
        
    if idx < len(tokens) and (tokens[idx] in ["q", "p", "—", "n/a"] or len(tokens[idx]) == 1):
        trend = tokens[idx]
        idx += 1
        
    rating_5yr = tokens[-1]
    rating_2024 = tokens[-2]
    
    # Validate rating format to ensure it's a valid rating line
    try:
        rating = float(rating_2024)
        if not (0.0 <= rating <= 10.0):
            return None
    except ValueError:
        return None
        
    middle_tokens = tokens[idx:-2]
    if not middle_tokens:
        return None
        
    # Split school name and city from middle_tokens
    school_name, city = None, None
    for n_words in [3, 2, 1]:
        if len(middle_tokens) > n_words:
            city_candidate = " ".join(middle_tokens[-n_words:])
            norm_candidate = re.sub(r"[^a-z0-9]", "", city_candidate.lower())
            if norm_candidate in known_cities:
                school_name = " ".join(middle_tokens[:-n_words])
                city = city_candidate
                break
                
    if school_name is None:
        school_name = " ".join(middle_tokens[:-1])
        city = middle_tokens[-1]
        
    # Clean up spacing artifacts
    school_name = clean_spacing(school_name)
    city = clean_spacing(city)
    
    # Standardize trend label
    trend_label = {"q": "improving", "p": "declining", "—": "stable"}.get(trend, trend)
    
    return {
        "rank": rank_2024,
        "last_rank": rank_5yr,
        "trend": trend_label,
        "name": school_name,
        "city": city,
        "rating": rating,
        "rating_5yr": rating_5yr
    }

def main():
    if not os.path.exists(PDF_PATH):
        print(f"PDF not found: {PDF_PATH}")
        return

    print(f"Reading PDF: {PDF_PATH}")
    reader = PdfReader(PDF_PATH)
    print(f"  {len(reader.pages)} pages found")

    known_cities = load_known_cities()
    print(f"  Loaded {len(known_cities)} unique city names for parsing")

    records = []
    seen = set()

    # The ranking tables are on pages 11 to 37 (index 11 to 37)
    for idx in range(11, 38):
        page = reader.pages[idx]
        left_frags = []
        right_frags = []
        
        def visitor(text, cm, tm, font_dict, font_size):
            txt = text.strip()
            if not txt:
                return
            x, y = tm[4], tm[5]
            # Split the page in the middle (x = 306)
            if x < 306:
                left_frags.append((x, y, txt))
            else:
                right_frags.append((x, y, txt))
                
        try:
            page.extract_text(visitor_text=visitor)
        except Exception as e:
            print(f"  Error extracting page {idx}: {e}")
            continue
            
        def get_lines(fragments):
            # Group fragments by y coordinate with 3 points tolerance
            fragments.sort(key=lambda f: -f[1])
            lines = []
            curr_line = []
            curr_y = None
            for x, y, txt in fragments:
                if curr_y is None:
                    curr_y = y
                    curr_line = [(x, txt)]
                elif abs(y - curr_y) <= 3:
                    curr_line.append((x, txt))
                else:
                    curr_line.sort(key=lambda item: item[0])
                    lines.append(" ".join(t for _, t in curr_line))
                    curr_y = y
                    curr_line = [(x, txt)]
            if curr_line:
                curr_line.sort(key=lambda item: item[0])
                lines.append(" ".join(t for _, t in curr_line))
            return lines

        left_lines = get_lines(left_frags)
        right_lines = get_lines(right_frags)
        
        for lines in [left_lines, right_lines]:
            for line in lines:
                r = parse_record_line(line, known_cities)
                if r:
                    key = (r["rank"], r["name"], r["city"])
                    if key not in seen:
                        seen.add(key)
                        records.append(r)

    print(f"  {len(records)} school records parsed")

    if not records:
        print("No records found — check PDF text extraction quality.")
        return

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    fieldnames = ["rank", "last_rank", "trend", "name", "city", "rating", "rating_5yr"]
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    rated = [r for r in records if r["rating"] is not None]
    ratings = [r["rating"] for r in rated]
    print(f"  Rating range: {min(ratings):.1f} – {max(ratings):.1f}")
    print(f"  Written to: {OUTPUT}")

    top5 = sorted(rated, key=lambda x: x["rating"], reverse=True)[:5]
    print("\nTop 5 schools parsed:")
    for r in top5:
        print(f"  {r['rating']} – {r['name']}, {r['city']}  (rank {r['rank']})")

if __name__ == "__main__":
    main()
