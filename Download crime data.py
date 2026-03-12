"""
Victorian Crime Data Downloader
=================================
Automatically downloads Criminal Incidents data from
the Crime Statistics Agency Victoria (files.crimestatistics.vic.gov.au).

Run this ONCE before running RandomCorrelations.py:
    python download_crime_data.py

It will download the most comprehensive available file
(Year Ending September 2025 — which contains data back to 2004)
and save it as crime_data.xlsx in the same folder.
"""

import os
import sys
import time
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "crime_data.xlsx")

# ─────────────────────────────────────────────────────────────────────────────
# Direct download URLs — most recent first, fallbacks below
# The September annual release contains the longest historical time series
# ─────────────────────────────────────────────────────────────────────────────
URLS = [
    # Sep 2025 — most recent, contains data back to 2004
    "https://files.crimestatistics.vic.gov.au/2025-12/Data_Tables_Criminal_Incidents_Visualisation_Year_Ending_September_2025.xlsx",
    # Sep 2024 — fallback
    "https://files.crimestatistics.vic.gov.au/2024-12/Data_Tables_Criminal_Incidents_Visualisation_Year_Ending_September_2024.xlsx",
    # Sep 2023 — fallback
    "https://files.crimestatistics.vic.gov.au/2023-12/Data_Tables_Criminal_Incidents_Visualisation_Year_Ending_September_2023.xlsx",
    # Mar 2025 — alternate
    "https://files.crimestatistics.vic.gov.au/2025-06/Data_Tables_Criminal_Incidents_Visualisation_Year_Ending_March_2025.xlsx",
]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
    "Referer": "https://www.crimestatistics.vic.gov.au/",
}


def download_file(url, dest_path):
    print(f"\n  Trying: {url.split('/')[-1]}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        if r.status_code == 200:
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded / total * 100
                            print(f"\r  Downloading... {pct:.0f}%  ({downloaded/1024:.0f} KB)", end="")
            print(f"\r  ✓ Downloaded {downloaded/1024:.0f} KB                    ")
            return True
        else:
            print(f"  ✗ HTTP {r.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    print("\n" + "═"*60)
    print("  Victorian Crime Data Downloader")
    print("  Crime Statistics Agency Victoria")
    print("═"*60)

    if os.path.exists(OUTPUT_FILE):
        size_kb = os.path.getsize(OUTPUT_FILE) / 1024
        print(f"\n  ✓ crime_data.xlsx already exists ({size_kb:.0f} KB)")
        resp = input("  Re-download? (y/n): ").strip().lower()
        if resp != "y":
            print("  Skipping download.")
            return

    success = False
    for url in URLS:
        if download_file(url, OUTPUT_FILE):
            success = True
            break
        time.sleep(2)

    if success:
        size_kb = os.path.getsize(OUTPUT_FILE) / 1024
        print(f"\n  ✓ Saved to: {OUTPUT_FILE}")
        print(f"  ✓ File size: {size_kb:.0f} KB")
        print("\n  You can now run RandomCorrelations.py")

        # Quick validation
        try:
            import pandas as pd
            xl = pd.ExcelFile(OUTPUT_FILE)
            print(f"\n  Sheets found in file:")
            for s in xl.sheet_names:
                print(f"    • {s}")
        except ImportError:
            pass
        except Exception as e:
            print(f"  Warning: Could not inspect file: {e}")
    else:
        print("\n  ✗ All download attempts failed.")
        print("\n  Please download manually:")
        print("  1. Go to: https://www.crimestatistics.vic.gov.au/crime-statistics/latest-victorian-crime-data/download-data")
        print("  2. Download: 'Data Tables Criminal Incidents Visualisation Year Ending September 2025'")
        print(f"  3. Save as: {OUTPUT_FILE}")

    print("\n" + "═"*60)


if __name__ == "__main__":
    main()
