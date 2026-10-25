"""
Live Climate Impact Dashboard - live data fetch

Open-Meteo (free, no API key) se aaj ka temperature aur air quality lata hai, aur
historical normal (city_monthly_normals.csv) se compare karke anomaly nikalta hai.

Usage:
    python fetch_live_data.py --out-dir powerbi_data

Pehle prepare_climate_data.py chala lo, taaki city_monthly_normals.csv ban jaye.
Requirements: pip install pandas   (baaki sab Python ke saath aata hai)

Output (out-dir me):
    live_latest.csv  - har baar overwrite hota hai (Power BI card/map ke liye)
    live_log.csv     - har run ki row append hoti hai (live trend ke liye)
"""

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pandas as pd

# ---- Apne cities yaha edit/add karo: (display name, latitude, longitude) ----
CITIES = [
    ("Delhi", 28.61, 77.21),
    ("Mumbai", 19.08, 72.88),
    ("Kolkata", 22.57, 88.36),
    ("Chennai", 13.08, 80.27),
    ("Bengaluru", 12.97, 77.59),
    ("London", 51.51, -0.13),
    ("New York", 40.71, -74.01),
    ("Tokyo", 35.68, 139.69),
]
MAX_MATCH_KM = 200   # normals wali city is distance ke andar honi chahiye


def http_json(url, params):
    full = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(full, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_weather(lat, lon):
    data = http_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "daily": "temperature_2m_mean",
        "forecast_days": 1, "timezone": "auto",
    })
    cur = data.get("current", {})
    daily = (data.get("daily", {}).get("temperature_2m_mean") or [None])[0]
    return {
        "CurrentTemp": cur.get("temperature_2m"),
        "TodayMeanTemp": daily,
        "Humidity": cur.get("relative_humidity_2m"),
        "WindSpeed": cur.get("wind_speed_10m"),
        "LocalTime": cur.get("time"),
    }


def fetch_air_quality(lat, lon):
    data = http_json("https://air-quality-api.open-meteo.com/v1/air-quality", {
        "latitude": lat, "longitude": lon,
        "current": "pm2_5,pm10,us_aqi", "timezone": "auto",
    })
    cur = data.get("current", {})
    return {"PM2_5": cur.get("pm2_5"), "PM10": cur.get("pm10"), "USAQI": cur.get("us_aqi")}


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def normal_for(normals, lat, lon, month):
    """Sabse paas wali dataset city ka us mahine ka normal temperature."""
    if normals is None:
        return None, None
    m = normals[normals["Month"] == month].dropna(subset=["Lat", "Lon"])
    if m.empty:
        return None, None
    dist = m.apply(lambda r: haversine_km(lat, lon, r["Lat"], r["Lon"]), axis=1)
    i = dist.idxmin()
    if dist[i] > MAX_MATCH_KM:
        return None, None
    return float(m.loc[i, "NormalTemp"]), f'{m.loc[i, "City"]}, {m.loc[i, "Country"]}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="powerbi_data")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    normals_path = os.path.join(args.out_dir, "city_monthly_normals.csv")
    normals = pd.read_csv(normals_path) if os.path.exists(normals_path) else None
    if normals is None:
        print("Note: city_monthly_normals.csv nahi mili - anomaly column khaali rahega. "
              "Pehle prepare_climate_data.py chalao.")

    now = datetime.now(timezone.utc)
    rows = []
    for name, lat, lon in CITIES:
        try:
            row = {"City": name, "Lat": lat, "Lon": lon}
            row.update(fetch_weather(lat, lon))
            try:
                row.update(fetch_air_quality(lat, lon))
            except (urllib.error.URLError, ValueError) as e:   # AQI fail ho to bhi weather rakho
                print(f"  {name}: air quality nahi mili ({e})")
            normal, matched = normal_for(normals, lat, lon, now.month)
            row["NormalTemp"] = normal
            row["NormalSource"] = matched
            ref = row.get("TodayMeanTemp")
            row["AnomalyVsNormal"] = round(ref - normal, 2) if (ref is not None and normal is not None) else None
            row["FetchedAtUTC"] = now.strftime("%Y-%m-%d %H:%M:%S")
            rows.append(row)
            print(f"  ok  {name}: {row.get('CurrentTemp')} C")
        except (urllib.error.URLError, ValueError, TimeoutError) as e:
            print(f"  FAIL {name}: {e}")

    if not rows:
        sys.exit("Koi bhi city fetch nahi hui. Internet connection check karo.")

    df = pd.DataFrame(rows)
    latest = os.path.join(args.out_dir, "live_latest.csv")
    log = os.path.join(args.out_dir, "live_log.csv")
    df.to_csv(latest, index=False)
    df.to_csv(log, mode="a", header=not os.path.exists(log), index=False)
    print(f"\nSaved {len(df)} cities -> {latest}")


if __name__ == "__main__":
    main()
