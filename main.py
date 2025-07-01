from flask import Flask, jsonify
import yfinance as yf
import pandas as pd
from google.cloud import bigquery
from datetime import datetime, timezone
from dotenv import load_dotenv
import os
import json
import time

# Load environment variables
load_dotenv()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

project_id = os.getenv("PROJECT_ID")
dataset_id = os.getenv("DATASET_ID")
table_id = os.getenv("TABLE_ID")
bq_table = f"{project_id}.{dataset_id}.{table_id}"

app = Flask(__name__)
client = bigquery.Client()

def safe_float(value):
    if hasattr(value, 'iloc'):
        value = value.iloc[0]
    if pd.isna(value):
        return None
    return float(value)

def download_with_retries(symbol, retries=3, delay=2):
    for attempt in range(retries):
        try:
            df = yf.download(symbol, period="7d", progress=False)
            if df.empty:
                raise ValueError("Empty dataframe")
            return df
        except Exception as e:
            print(f"Attempt {attempt+1} failed for {symbol}: {e}")
            time.sleep(delay)
    return None

@app.route("/", methods=["GET", "POST"])
def risk_monitor():
    today = datetime.now(timezone.utc).date()

    with open("portfolio.json", "r") as f:
        portfolio = json.load(f)

    results = []

    for stock in portfolio:
        symbol = stock["symbol"]
        quantity = stock["quantity"]
        asset_type = stock["type"]

        df = download_with_retries(symbol)
        if df is None or len(df["Close"]) < 5:
            print(f"Skipping {symbol} — insufficient or no data after retries")
            continue

        price_today = df["Close"].iloc[-1]
        price_yesterday = df["Close"].iloc[-2]
        pnl = (price_today - price_yesterday) * quantity

        returns = df["Close"].pct_change()
        volatility = safe_float(returns.rolling(5).std().iloc[-1])

        if volatility is None:
            print(f"Skipping {symbol} — volatility calculation failed")
            continue

        margin_rate = (
            0.05 if volatility < 0.01 else
            0.10 if volatility < 0.02 else
            0.20
        )
        margin = price_today * quantity * margin_rate

        pnl = float(pnl)
        margin = float(margin)
        volatility = float(volatility)

        breach = (abs(pnl) > 500) or (margin > 5000) or (volatility > 0.03)

        results.append({
            "symbol": symbol,
            "date": str(today),
            "pnl": round(pnl, 2),
            "volatility": round(volatility, 4),
            "margin": round(margin, 2),
            "type": asset_type,
            "breach": breach
        })

    if results:
        errors = client.insert_rows_json(bq_table, results)
        if errors:
            return jsonify({"error": errors}), 500
        return jsonify({"message": "Success", "records_inserted": len(results)}), 200
    else:
        return jsonify({"message": "No valid data to insert"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
