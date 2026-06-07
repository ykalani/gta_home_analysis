"""
Downloads and processes Fraser Institute Ontario Elementary School Rankings.
Run once before starting the app: python fetch_fraser_data.py
"""

import requests
import pandas as pd
import os

FRASER_URL = "https://www.fraserinstitute.org/sites/default/files/ontario-2023-elementary-school-ratings.xlsx"

FALLBACK_URLS = [
    "https://www.fraserinstitute.org/sites/default/files/ontario-elementary-school-ratings-2023.xlsx",
    "https://www.fraserinstitute.org/sites/default/files/ontario-2022-elementary-school-ratings.xlsx",
]

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "data", "fraser_schools.csv")


def download_fraser_data():
    headers = {"User-Agent": "Mozilla/5.0"}
    urls = [FRASER_URL] + FALLBACK_URLS
    raw_path = os.path.join(os.path.dirname(__file__), "data", "fraser_raw.xlsx")

    for url in urls:
        print(f"Trying {url} ...")
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200 and b"PK" in r.content[:4]:  # valid xlsx
                with open(raw_path, "wb") as f:
                    f.write(r.content)
                print("Downloaded successfully.")
                return raw_path
        except Exception as e:
            print(f"  Failed: {e}")

    return None


def process_excel(raw_path):
    # Try reading — Fraser Institute files vary by year; attempt common layouts
    xf = pd.ExcelFile(raw_path)
    print(f"Sheets found: {xf.sheet_names}")

    df = pd.read_excel(raw_path, sheet_name=xf.sheet_names[0], header=None)

    # Find header row (contains "School Name" or "School")
    header_row = None
    for i, row in df.iterrows():
        vals = [str(v).lower() for v in row.values]
        if any("school" in v for v in vals):
            header_row = i
            break

    if header_row is None:
        raise ValueError("Could not find header row in Fraser Institute Excel file.")

    df.columns = df.iloc[header_row]
    df = df.iloc[header_row + 1 :].reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]

    print(f"Columns: {list(df.columns)}")

    # Normalize column names
    col_map = {}
    for col in df.columns:
        cl = col.lower()
        if "school name" in cl or (col_map.get("name") is None and "school" in cl and "board" not in cl and "type" not in cl):
            col_map["name"] = col
        elif "city" in cl or "municipality" in cl:
            col_map["city"] = col
        elif "address" in cl:
            col_map["address"] = col
        elif "rating" in cl and "overall" in cl:
            col_map["rating"] = col
        elif "rating" in cl and col_map.get("rating") is None:
            col_map["rating"] = col
        elif "rank" in cl and col_map.get("rating") is None:
            col_map["rating"] = col
        elif "postal" in cl or "post" in cl:
            col_map["postal"] = col
        elif "province" in cl or "prov" in cl:
            col_map["province"] = col

    print(f"Column mapping: {col_map}")

    if "name" not in col_map:
        raise ValueError("Could not identify school name column.")

    keep = {v: k for k, v in col_map.items()}
    df = df[[c for c in keep if c in df.columns]].rename(columns=keep)

    # Filter to elementary schools only (Fraser data usually has a type/level column)
    if "type" in df.columns:
        df = df[df["type"].str.lower().str.contains("elem", na=False)]

    df = df.dropna(subset=["name"])
    df["rating"] = pd.to_numeric(df.get("rating", pd.Series()), errors="coerce")

    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Saved {len(df)} schools to {OUTPUT_PATH}")


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    raw_path = download_fraser_data()
    if raw_path:
        process_excel(raw_path)
    else:
        print("\nAutomatic download failed.")
        print("Please download the Ontario Elementary School Rankings Excel file from:")
        print("  https://www.fraserinstitute.org/report-cards/school-report-cards/ontario")
        print(f"Then save it as: {os.path.join(os.path.dirname(OUTPUT_PATH), 'fraser_raw.xlsx')}")
        print("Then re-run this script.")
