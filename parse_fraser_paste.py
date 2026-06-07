"""
Paste Fraser Institute school data directly into fraser_data.txt,
then run: py parse_fraser_paste.py

Handles the PDF-extracted format:
  rank  last_rank  trend  school_name...  city...  rating_2024  rating_last
"""

import re
import csv
import os

INPUT_FILE  = os.path.join(os.path.dirname(__file__), "fraser_data.txt")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "data", "fraser_schools.csv")

# Lines that are page headers/footers to skip
SKIP_PATTERNS = [
    re.compile(r"Fraser Institute"),
    re.compile(r"Report Card on Ontario"),
    re.compile(r"^—+"),
    re.compile(r"Rank"),
    re.compile(r"Overall rating"),
    re.compile(r"School name"),
    re.compile(r"^\s*$"),
    # rotated header characters repeated pattern
    re.compile(r"^[A-Za-z\s]{1,3}$"),
]

# A valid data line starts with a 1-4 digit rank number
DATA_LINE = re.compile(r"^(\d{1,4})\s+")

def is_skip(line):
    for pat in SKIP_PATTERNS:
        if pat.search(line):
            return True
    return False

def parse_line(line):
    """
    Returns dict with keys: rank, name, city, rating, last_rank, trend
    or None if the line can't be parsed.
    """
    line = line.strip()
    if not line:
        return None
    if not DATA_LINE.match(line):
        return None
    if is_skip(line):
        return None

    tokens = line.split()

    # Need at least: rank last_rank trend school_word city_word rating rating_last = 7 tokens
    if len(tokens) < 7:
        return None

    rank = tokens[0]

    # last_rank is tokens[1] — either a number or "n/a"
    last_rank = tokens[1]

    # trend is tokens[2] — q, p, —, or "n/a"
    trend = tokens[2]

    # Last token is rating_last (number or "n/a")
    rating_last = tokens[-1]

    # Second-to-last token is rating_2024
    rating_2024 = tokens[-2]

    # Everything in between is school + city
    middle = tokens[3:-2]
    if not middle:
        return None

    # Keep the full "school name + city" as the name field.
    # The app matches by word overlap so city words don't hurt.
    name = " ".join(middle)
    city = ""

    # rating_2024 must be a number
    try:
        rating = float(rating_2024)
    except ValueError:
        rating = None

    return {
        "rank":      rank,
        "name":      name,
        "city":      city,
        "rating":    rating,
        "last_rank": last_rank,
        "trend":     trend,
    }


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: {INPUT_FILE} not found.")
        print("Create fraser_data.txt and paste all the Fraser Institute pages into it, then re-run.")
        return

    rows = []
    skipped = 0
    with open(INPUT_FILE, encoding="utf-8") as f:
        for raw in f:
            parsed = parse_line(raw)
            if parsed:
                rows.append(parsed)
            elif raw.strip() and DATA_LINE.match(raw.strip()):
                skipped += 1

    if not rows:
        print("No rows parsed. Check that fraser_data.txt contains the pasted Fraser data.")
        return

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["rank","name","city","rating","last_rank","trend"])
        writer.writeheader()
        writer.writerows(rows)

    rated = sum(1 for r in rows if r["rating"] is not None)
    print(f"Parsed {len(rows)} schools ({rated} with ratings) -> {OUTPUT_FILE}")
    if skipped:
        print(f"Skipped {skipped} lines that looked like data but couldn't be parsed.")

    # Show rating distribution so user can see if top schools are missing
    if rows:
        ratings = [r["rating"] for r in rows if r["rating"] is not None]
        print(f"Rating range in file: {min(ratings):.1f} – {max(ratings):.1f}")
        top10 = sorted(rows, key=lambda x: x["rating"] or 0, reverse=True)[:5]
        print("\nTop 5 schools in this data:")
        for r in top10:
            print(f"  {r['rating']} – {r['name']}, {r['city']}")


if __name__ == "__main__":
    main()
