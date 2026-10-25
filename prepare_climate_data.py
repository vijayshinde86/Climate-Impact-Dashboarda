"""
Live Climate Impact Dashboard - data preparation script

Berkeley Earth "Global Land Temperatures" CSV files ko load karta hai, clean karta hai,
aur Power BI ke liye chhoti yearly CSV files banata hai.

Usage:
    python prepare_climate_data.py --data-dir "C:/path/to/csv/folder" --out-dir powerbi_data

Requirements:
    pip install pandas

Jo file folder me nahi milegi, script us ko skip kar dega (baaki chalte rahenge).
"""

import argparse
import os
import re
import sys

import pandas as pd

MIN_MONTHS = 10          # ek saal ko valid maanne ke liye kam se kam itne months ka data
BASE_START, BASE_END = 1951, 1980    # baseline period (anomaly ke liye)
RECENT_START, RECENT_END = 1991, 2013  # recent period (warming ke liye)
CITY_MIN_YEAR = 1900     # ByCity se output chhota rakhne ke liye sirf 1900 ke baad
CHUNK_SIZE = 1_000_000


# ---------------------------------------------------------------- helpers
def path_of(data_dir, name):
    p = os.path.join(data_dir, name)
    return p if os.path.exists(p) else None


def parse_coord(value):
    """'57.05N' -> 57.05 , '10.33W' -> -10.33"""
    if pd.isna(value):
        return None
    m = re.match(r"^\s*([0-9.]+)\s*([NSEW])\s*$", str(value))
    if not m:
        return None
    num = float(m.group(1))
    return -num if m.group(2) in ("S", "W") else num


def clean_country(name):
    """'Denmark (Europe)' -> 'Denmark' (Power BI map ke liye)."""
    return re.sub(r"\s*\((Europe|Africa|Asia|North America|South America|Oceania)\)\s*$", "", str(name)).strip()


def add_year(df):
    df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
    df = df.dropna(subset=["dt"]).copy()
    df["Year"] = df["dt"].dt.year
    return df


def yearly_mean(df, group_cols, value_col="AverageTemperature", unc_col="AverageTemperatureUncertainty"):
    """Monthly -> yearly average. Jis saal me MIN_MONTHS se kam months ho, wo hata deta hai."""
    df = df.dropna(subset=[value_col])
    agg = {
        "AvgTemp": (value_col, "mean"),
        "Months": (value_col, "count"),
    }
    if unc_col in df.columns:
        agg["Uncertainty"] = (unc_col, "mean")
    out = df.groupby(group_cols + ["Year"], as_index=False).agg(**agg)
    out = out[out["Months"] >= MIN_MONTHS].drop(columns="Months")
    return out.round(3)


def add_decade(df):
    df["Decade"] = (df["Year"] // 10 * 10).astype(int)
    return df


def warming_table(yearly, key_cols):
    """Recent period avg - baseline period avg, har key (country/state/city) ke liye."""
    base = yearly[yearly["Year"].between(BASE_START, BASE_END)].groupby(key_cols)["AvgTemp"].mean().rename("BaselineAvg")
    recent = yearly[yearly["Year"].between(RECENT_START, RECENT_END)].groupby(key_cols)["AvgTemp"].mean().rename("RecentAvg")
    w = pd.concat([base, recent], axis=1).dropna().reset_index()
    w["Warming"] = w["RecentAvg"] - w["BaselineAvg"]
    return w.round(3).sort_values("Warming", ascending=False)


def save(df, out_dir, name):
    path = os.path.join(out_dir, name)
    df.to_csv(path, index=False)
    print(f"  saved {name:<28} {len(df):>9,} rows")


# ---------------------------------------------------------------- processors
def process_global(data_dir, out_dir):
    p = path_of(data_dir, "GlobalTemperatures.csv")
    if not p:
        print("[skip] GlobalTemperatures.csv nahi mili")
        return
    print("[1/5] GlobalTemperatures")
    df = add_year(pd.read_csv(p))
    g = df.groupby("Year")
    out = pd.DataFrame({
        "LandAvgTemp": g["LandAverageTemperature"].mean(),
        "LandMaxTemp": g["LandMaxTemperature"].mean(),
        "LandMinTemp": g["LandMinTemperature"].mean(),
        "LandOceanAvgTemp": g["LandAndOceanAverageTemperature"].mean(),
        "Uncertainty": g["LandAverageTemperatureUncertainty"].mean(),
        "Months": g["LandAverageTemperature"].count(),
    }).reset_index()
    out = out[out["Months"] >= MIN_MONTHS].drop(columns="Months")
    base = out.loc[out["Year"].between(BASE_START, BASE_END), "LandAvgTemp"].mean()
    out["Anomaly"] = out["LandAvgTemp"] - base          # 1951-1980 average se difference
    out["UpperBand"] = out["LandAvgTemp"] + out["Uncertainty"]
    out["LowerBand"] = out["LandAvgTemp"] - out["Uncertainty"]
    out = add_decade(out).round(3)
    save(out, out_dir, "global_yearly.csv")


def process_country(data_dir, out_dir):
    p = path_of(data_dir, "GlobalLandTemperaturesByCountry.csv")
    if not p:
        print("[skip] GlobalLandTemperaturesByCountry.csv nahi mili")
        return
    print("[2/5] ByCountry")
    df = add_year(pd.read_csv(p))
    df["Country"] = df["Country"].map(clean_country)
    yearly = add_decade(yearly_mean(df, ["Country"]))
    save(yearly, out_dir, "country_yearly.csv")
    save(warming_table(yearly, ["Country"]), out_dir, "country_warming.csv")


def process_major_city(data_dir, out_dir):
    p = path_of(data_dir, "GlobalLandTemperaturesByMajorCity.csv")
    if not p:
        print("[skip] GlobalLandTemperaturesByMajorCity.csv nahi mili")
        return
    print("[3/5] ByMajorCity")
    df = add_year(pd.read_csv(p))
    df["Country"] = df["Country"].map(clean_country)
    df["Lat"] = df["Latitude"].map(parse_coord)
    df["Lon"] = df["Longitude"].map(parse_coord)
    coords = df.drop_duplicates(["City", "Country"])[["City", "Country", "Lat", "Lon"]]
    yearly = yearly_mean(df, ["City", "Country"])
    yearly = add_decade(yearly.merge(coords, on=["City", "Country"], how="left"))
    save(yearly, out_dir, "major_city_yearly.csv")
    save(warming_table(yearly, ["City", "Country"]).merge(coords, on=["City", "Country"], how="left"),
         out_dir, "major_city_warming.csv")

    # Mahine-wise normal temperature (1981-2013) - live temperature se compare karne ke liye
    m = df.dropna(subset=["AverageTemperature"])
    m = m[m["Year"].between(1981, 2013)].copy()
    m["Month"] = m["dt"].dt.month
    clim = (m.groupby(["City", "Country", "Month"], as_index=False)["AverageTemperature"].mean()
              .rename(columns={"AverageTemperature": "NormalTemp"}).round(3)
              .merge(coords, on=["City", "Country"], how="left"))
    save(clim, out_dir, "city_monthly_normals.csv")


def process_state(data_dir, out_dir):
    p = path_of(data_dir, "GlobalLandTemperaturesByState.csv")
    if not p:
        print("[skip] GlobalLandTemperaturesByState.csv nahi mili")
        return
    print("[4/5] ByState")
    df = add_year(pd.read_csv(p))
    df["Country"] = df["Country"].map(clean_country)
    yearly = add_decade(yearly_mean(df, ["State", "Country"]))
    save(yearly, out_dir, "state_yearly.csv")
    india = yearly[yearly["Country"] == "India"]
    if len(india):
        save(india, out_dir, "india_state_yearly.csv")
        save(warming_table(india, ["State", "Country"]), out_dir, "india_state_warming.csv")


def process_city(data_dir, out_dir):
    p = path_of(data_dir, "GlobalLandTemperaturesByCity.csv")
    if not p:
        print("[skip] GlobalLandTemperaturesByCity.csv nahi mili")
        return
    print("[5/5] ByCity (badi file, chunks me padh raha hu - thoda time lagega)")
    parts, coord_parts = [], []
    cols = ["dt", "AverageTemperature", "City", "Country", "Latitude", "Longitude"]
    for i, chunk in enumerate(pd.read_csv(p, usecols=cols, chunksize=CHUNK_SIZE), start=1):
        chunk = add_year(chunk)
        chunk = chunk[chunk["Year"] >= CITY_MIN_YEAR]
        coord_parts.append(chunk.drop_duplicates(["City", "Country"])[["City", "Country", "Latitude", "Longitude"]])
        chunk = chunk.dropna(subset=["AverageTemperature"])
        parts.append(chunk.groupby(["City", "Country", "Year"])["AverageTemperature"]
                     .agg(Total="sum", Months="count").reset_index())
        print(f"   chunk {i} done")
    if not parts:
        return
    agg = pd.concat(parts).groupby(["City", "Country", "Year"], as_index=False).sum()
    agg = agg[agg["Months"] >= MIN_MONTHS]
    agg["AvgTemp"] = (agg["Total"] / agg["Months"]).round(3)
    agg = agg.drop(columns=["Total", "Months"])
    agg["Country"] = agg["Country"].map(clean_country)

    coords = pd.concat(coord_parts).drop_duplicates(["City", "Country"]).copy()
    coords["Lat"] = coords["Latitude"].map(parse_coord)
    coords["Lon"] = coords["Longitude"].map(parse_coord)
    coords["Country"] = coords["Country"].map(clean_country)
    coords = coords[["City", "Country", "Lat", "Lon"]].drop_duplicates(["City", "Country"])

    agg = add_decade(agg.merge(coords, on=["City", "Country"], how="left"))
    save(agg, out_dir, "city_yearly.csv")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Climate CSVs ko Power BI ke liye prepare karo")
    ap.add_argument("--data-dir", default=".", help="CSV files wala folder")
    ap.add_argument("--out-dir", default="powerbi_data", help="Output folder")
    ap.add_argument("--skip-city", action="store_true", help="Badi ByCity file skip karo")
    args = ap.parse_args()

    if not os.path.isdir(args.data_dir):
        sys.exit(f"Folder nahi mila: {args.data_dir}")
    os.makedirs(args.out_dir, exist_ok=True)

    process_global(args.data_dir, args.out_dir)
    process_country(args.data_dir, args.out_dir)
    process_major_city(args.data_dir, args.out_dir)
    process_state(args.data_dir, args.out_dir)
    if not args.skip_city:
        process_city(args.data_dir, args.out_dir)

    print(f"\nDone. Output files yaha hain: {os.path.abspath(args.out_dir)}")


if __name__ == "__main__":
    main()
