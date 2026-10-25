# Live Climate Impact Dashboard

Historical climate data (Berkeley Earth Global Land Temperatures) + live weather/air quality
(Open-Meteo API) ko ek Power BI dashboard me dikhane wala data analytics project.

## Tech stack
Python, Pandas, Open-Meteo API, Power BI, DAX

## Folder structure
```
data/raw/        -> original 5 CSV files yaha rakho
data/processed/  -> script ke output (Power BI inhe import karta hai)
src/             -> Python scripts
powerbi/         -> DAX measures aur .pbix file
docs/            -> screenshots, notes
```

## Setup
```
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Run
```
python src/prepare_climate_data.py --data-dir data/raw --out-dir data/processed
python src/fetch_live_data.py --out-dir data/processed
```
Phir Power BI me `data/processed` ki CSVs import karo aur `powerbi/dax_measures.txt` ke measures paste karo.

## Data source
- Berkeley Earth Surface Temperature Data (Kaggle) - historical, 1750 se ~2013/2015 tak
- Open-Meteo - live temperature aur air quality (API key nahi chahiye)
