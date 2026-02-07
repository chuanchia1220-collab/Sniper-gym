import pandas as pd
import numpy as np
import json
import random
from logger import log_error
import datetime

EXAMS_FILE = "exams.json"

def load_exam_data(filepath=EXAMS_FILE):
    """
    Reads the exams.json file and returns a list of questions.
    """
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
        return data
    except Exception as e:
        log_error(e, "load_exam_data")
        return []

def filter_questions(data, mode):
    """
    Filters the list of questions based on the selected game mode.
    """
    if mode == "Realistic":
        return [q for q in data if q.get("level") == "Real"]
    return [q for q in data if q.get("level") == mode]

def calculate_result(action, question_data):
    """
    Determines if the user's action was correct and calculates mock PnL.
    """
    correct_action = question_data.get("correct_action")

    # Simple logic for now
    is_correct = action == correct_action

    pnl = 0.0
    if is_correct:
        if action == "Pass":
            pnl = 0.0
        else:
             # Random profit between 1% and 5% for successful trades
            pnl = random.uniform(1.0, 5.0)
    else:
        if action == "Pass":
             # Missed opportunity cost (virtual loss)
            pnl = -random.uniform(0.5, 2.0)
        else:
             # Loss on bad trade
            pnl = -random.uniform(1.0, 3.0)

    return is_correct, round(pnl, 2)


def generate_mock_data(ticker, date_str, timestamp_str):
    """
    Generates realistic-looking mock OHLCV data + VWAP for Stock and Index.
    Returns two DataFrames: stock_df, index_df
    """
    try:
        # Create a time range for the trading day (09:00 to 13:30)
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        start_time = datetime.datetime.combine(date, datetime.time(9, 0))
        end_time = datetime.datetime.combine(date, datetime.time(13, 30))
        freq = "1min"

        time_index = pd.date_range(start=start_time, end=end_time, freq=freq)
        n = len(time_index)

        # --- Generate Mock Stock Data ---
        # Random walk with drift
        start_price = 100.0  # Base price
        volatility = 0.2
        returns = np.random.normal(loc=0.0001, scale=volatility, size=n)
        price_path = start_price * np.cumprod(1 + returns)

        # OHLC simulation
        opens = price_path
        closes = price_path * (1 + np.random.normal(0, 0.05, n))
        highs = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, 0.02, n)))
        lows = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, 0.02, n)))
        volumes = np.random.randint(100, 5000, size=n)

        stock_df = pd.DataFrame({
            "Time": time_index,
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes
        })

        # Calculate VWAP
        # VWAP = Cumulative(Price * Volume) / Cumulative(Volume)
        # Using Typical Price (H+L+C)/3 for VWAP calculation is common
        typical_price = (stock_df["High"] + stock_df["Low"] + stock_df["Close"]) / 3
        stock_df["VWAP"] = (typical_price * stock_df["Volume"]).cumsum() / stock_df["Volume"].cumsum()

        # --- Generate Mock Index Data (^TWII) ---
        # Correlated but distinct path
        index_start = 16000.0
        index_volatility = 0.1
        index_returns = np.random.normal(loc=0.00005, scale=index_volatility, size=n)
        index_path = index_start * np.cumprod(1 + index_returns)

        index_df = pd.DataFrame({
            "Time": time_index,
            "Close": index_path
        })

        return stock_df, index_df

    except Exception as e:
        log_error(e, f"generate_mock_data for {ticker}")
        return pd.DataFrame(), pd.DataFrame()
