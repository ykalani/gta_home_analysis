"""
Parse the Fraser Institute PDF directly into data/fraser_schools.csv using a robust
token-based multi-column parsing algorithm.
Run: py parse_fraser_pdf.py
"""

import re
import csv
import os
from pypdf import PdfReader

PDF_PATH = os.path.join(os.path.dirname(__file__), "data", "ontario-elementary-school-rankings-2025.pdf")
OUTPUT   = os.path.join(os.path.dirname(__file__), "data", "fraser_schools.csv")

TRENDS = {"", "p", "q", "—", "n/a"}

# Header/footer patterns to skip
SKIP_RE = re.compile(
    r"Fraser Institute|Report Card on Ontario|Overall rating|School name|"
    r"^\s*—+\s*$|^\s*Rank\s*$|^\s*$|^[A-Za-z\s]{1,4}$|"
    r"Last|2023|2024|Trend|City|yrs|Studies in Education"
)

def is_rank(token):
    return token.isdigit()

def is_last_rank(token):
    return token.isdigit() or token == "n/a"

def is_trend(token):
    return token in TRENDS or len(token) == 1

def parse_record_tokens(tokens):
    if len(tokens) < 5:
        return None
    rank = tokens[0]
    last_rank = tokens[1]
    trend = tokens[2]
    
    rating_5yr = tokens[-1]
    rating_2024 = tokens[-2]
    
    middle = tokens[3:-2]
    if not middle:
        return None
        
    # Standardize trend representation
    trend_label = {"q": "improving", "p": "declining", "—": "stable"}.get(trend, trend)
    
    city = middle[-1]
    name = " ".join(middle[:-1]) if len(middle) > 1 else middle[0]
    
    try:
        rating = float(rating_2024)
    except ValueError:
        rating = None
        
    return {
        "rank": rank,
        "last_rank": last_rank,
        "trend": trend_label,
        "name": name,
        "city": city,
        "rating": rating,
        "rating_5yr": rating_5yr
    }

def parse_line_tokens(line):
    tokens = line.strip().split()
    if len(tokens) < 5:
        return []
        
    # Check if the line has a second record
    split_idx = None
    for i in range(5, len(tokens) - 4):
        if is_rank(tokens[i]) and is_last_rank(tokens[i+1]) and is_trend(tokens[i+2]):
            split_idx = i
            break
            
    if split_idx is not None:
        left_tokens = tokens[:split_idx]
        right_tokens = tokens[split_idx:]
        left_rec = parse_record_tokens(left_tokens)
        right_rec = parse_record_tokens(right_tokens)
        return [r for r in [left_rec, right_rec] if r is not None]
    else:
        # Just one record on the line
        rec = parse_record_tokens(tokens)
        if rec and rec["rank"].isdigit():
            return [rec]
        return []

def main():
    if not os.path.exists(PDF_PATH):
        print(f"PDF not found: {PDF_PATH}")
        return

    print(f"Reading PDF: {PDF_PATH}")
    reader = PdfReader(PDF_PATH)
    print(f"  {len(reader.pages)} pages found")

    records = []
    seen = set()

    for idx in range(11, 38):
        page = reader.pages[idx]
        try:
            # Layout mode keeps columns aligned horizontally
            text = page.extract_text(extraction_mode="layout")
        except Exception:
            try:
                text = page.extract_text()
            except Exception:
                continue
        if not text:
            continue
            
        for line in text.splitlines():
            line_stripped = line.strip()
            if not line_stripped:
                continue
            if SKIP_RE.search(line_stripped):
                continue
            # Must start with a digit rank (possibly with leading whitespace)
            if not re.match(r"^\s*\d{1,4}\s", line):
                continue
                
            recs = parse_line_tokens(line)
            for r in recs:
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
