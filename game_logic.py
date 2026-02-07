import pandas as pd
import numpy as np
import json
import random
from logger import log_error
import datetime

EXAMS_FILE = "exams.json"

def load_exam_data(filepath=EXAMS_FILE):
    try:
        with open(filepath, "r", encoding='utf-8') as f: # Add utf-8 for Chinese characters
            data = json.load(f)
        return data
    except Exception as e:
        log_error(e, "load_exam_data")
        return []

def filter_questions(data, mode):
    if mode == "Realistic":
        return [q for q in data if q.get("level") == "Real"]
    return [q for q in data if q.get("level") == mode]

def calculate_result(action, question_data):
    correct_action = question_data.get("correct_action")
    is_correct = action == correct_action
    
    # Enhanced PnL Logic
    pnl = 0.0
    if is_correct:
        if action == "Pass": pnl = 0.0
        else: pnl = random.uniform(1.5, 6.0) # Reward good trades
    else:
        if action == "Pass": pnl = -random.uniform(0.5, 1.5) # Opportunity cost
        else: pnl = -random.uniform(2.0, 5.0) # Punish bad trades
        
    return is_correct, round(pnl, 2)

def generate_mock_data(ticker, date_str, timestamp_str, scenario_type=None, correct_action=None):
    """
    Generates mock data that loosely fits the scenario description.
    """
    try:
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        start_time = datetime.datetime.combine(date, datetime.time(9, 0))
        # End time is slightly after the decision point to show context
        decision_time = datetime.datetime.strptime(f"{date_str} {timestamp_str}", "%Y-%m-%d %H:%M")
        end_time = decision_time + datetime.timedelta(minutes=30) 
        
        freq = "1min"
        time_index = pd.date_range(start=start_time, end=end_time, freq=freq)
        n = len(time_index)

        # --- Smart Mock Logic ---
        # 1. Base Trend
        trend = 0.0002 if correct_action == "Buy" else -0.0002 if correct_action == "Sell" else 0
        
        # 2. Volatility
        volatility = 0.002 # 0.2% per minute
        
        # 3. Generate Returns
        returns = np.random.normal(loc=trend, scale=volatility, size=n)
        
        # **Crucial**: Inject the specific pattern at the decision time
        decision_idx = time_index.get_loc(decision_time) if decision_time in time_index else n-5
        
        # Apply pattern based on action (Simple heuristic)
        if correct_action == "Buy":
            # Ramp up before decision
            returns[decision_idx-3:decision_idx] = 0.005 # Strong push
        elif correct_action == "Sell":
            # Fake breakout then drop
            returns[decision_idx-3] = 0.005
            returns[decision_idx-1] = -0.008 
            
        start_price = 100.0
        price_path = start_price * np.cumprod(1 + returns)

        # OHLC Construction
        opens = price_path
        closes = price_path * (1 + np.random.normal(0, 0.001, n))
        highs = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, 0.001, n)))
        lows = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, 0.001, n)))
        
        # Volume Spike at decision
        volumes = np.random.randint(100, 1000, size=n)
        volumes[decision_idx-2:decision_idx+1] = np.random.randint(2000, 5000, size=3)

        stock_df = pd.DataFrame({
            "Time": time_index,
            "Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes
        })

        # VWAP
        typical_price = (stock_df["High"] + stock_df["Low"] + stock_df["Close"]) / 3
        stock_df["VWAP"] = (typical_price * stock_df["Volume"]).cumsum() / stock_df["Volume"].cumsum()

        # Mock Index
        index_start = 16000.0
        index_returns = np.random.normal(loc=0, scale=0.001, size=n)
        if "Tailwind" in str(scenario_type): index_returns += 0.0002
        elif "Headwind" in str(scenario_type): index_returns -= 0.0002
            
        index_path = index_start * np.cumprod(1 + index_returns)
        index_df = pd.DataFrame({"Time": time_index, "Close": index_path})

        return stock_df, index_df

    except Exception as e:
        log_error(e, f"generate_mock_data for {ticker}")
        return pd.DataFrame(), pd.DataFrame()
