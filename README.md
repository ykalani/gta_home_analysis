# Toronto Listing Analyzer

Paste a ReMax listing address and instantly see:
- Nearby elementary schools with **Fraser Institute ratings**
- Detailed vertical transit timeline breakdown to **Union Station** (powered by Google Maps Directions API)

## Setup

### 1. Install dependencies
```
pip install -r requirements.txt
```

### 2. Get a Google Maps API Key
1. Go to https://console.cloud.google.com/
2. Create a project → Enable these APIs:
   - **Geocoding API**
   - **Directions API**
3. Create an API key under Credentials

### 3. Get Fraser Institute school data
Run the downloader (tries to fetch automatically):
```
python fetch_fraser_data.py
```
If automatic download fails, go to:
https://www.fraserinstitute.org/report-cards/school-report-cards/ontario
Download the Ontario Elementary School Rankings Excel file, save it as `data/fraser_raw.xlsx`, then re-run.

### 4. Run the app
Set the API key as an environment variable and run the Flask server:

On Windows (PowerShell):
```powershell
$env:GOOGLE_MAPS_API_KEY="your_api_key_here"
python app.py
```

On macOS/Linux:
```bash
export GOOGLE_MAPS_API_KEY="your_api_key_here"
python app.py
```

Then visit `http://127.0.0.1:5000` in your web browser.

## Notes
- School matching queries OpenStreetMap/Overpass API for nearby schools, then fuzzy-matches names against the Fraser dataset.
- Transit routes are requested dynamically using the real-time Google Maps Directions API, producing a detailed walk and transit step-by-step breakdown.
- The Fraser Institute publishes ratings from 1–10 for each school based on academic performance (EQAO test results).
