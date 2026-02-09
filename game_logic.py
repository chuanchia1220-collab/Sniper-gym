import pandas as pd
import numpy as np
import json
import yfinance as yf
import streamlit as st
from logger import log_error
import datetime
from datetime import timedelta
import random

EXAMS_FILE = "exams.json"

def load_exam_data(filepath=EXAMS_FILE):
    """
    Reads the exams.json file and returns a list of questions.
    """
    try:
        with open(filepath, "r", encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        log_error(e, "load_exam_data")
        return []

def filter_questions(data, mode):
    """
    Filters questions based on the selected game mode.
    Maps UI modes to JSON levels.
    """
    # Map "Realistic" in UI to "Real" in JSON if needed, 
    # but based on your exams.json, levels are "Easy", "Medium", "Hard", "Real".
    if mode == "Realistic":
        return [q for q in data if q.get("level") == "Real"]
    
    # Fallback: exact match (Easy, Medium, Hard)
    return [q for q in data if q.get("level") == mode]

def calculate_result(action, question_data):
    """
    Determines if the user's action was correct based on the exam data.
    """
    correct_action = question_data.get("correct_action")
    is_correct = action == correct_action
    
    # PnL Logic:
    # Since we are using REAL scenarios determined by the Hunter,
    # we simulate the PnL reward based on the difficulty/correctness.
    # In a full version, we could calculate exact PnL from the dataframe, 
    # but for gameplay fluidity, we use a reward system here.
    
    pnl = 0.0
    if is_correct:
        if action == "Pass": 
            pnl = 0.0
        else: 
            # Reward: 1.5% ~ 4.0% profit for correct calls
            pnl = round(random.uniform(1.5, 4.0), 2)
    else:
        if action == "Pass": 
            # Missed opportunity (Paper cut)
            pnl = round(-random.uniform(0.5, 1.0), 2)
        else: 
            # Wrong trade (Loss)
            pnl = round(-random.uniform(1.5, 3.5), 2)
        
    return is_correct, pnl

@st.cache_data(ttl=3600) # Cache for 1 hour to prevent API spamming
def get_real_data(ticker, date_str):
    """
    Fetches 1m data for the specific ticker and market index (^TWII).
    Returns (stock_df, index_df).
    
    NOTE: yfinance 1m data is limited to the last 30 days. 
    If date is older, it might return empty.
    """
    try:
        start_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        # yfinance end_date is exclusive, so we add 1 day
        end_date = start_date + datetime.timedelta(days=1)
        
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        # --- 1. Fetch Stock Data ---
        # auto_adjust=True handles splits/dividends better
        stock_df = yf.download(ticker, start=start_str, end=end_str, interval="1m", progress=False, auto_adjust=True)
        
        if stock_df.empty:
            return pd.DataFrame(), pd.DataFrame()

        # Handle MultiIndex Columns (Fix for yfinance updates)
        if isinstance(stock_df.columns, pd.MultiIndex):
            try:
                stock_df.columns = stock_df.columns.droplevel(1)
            except:
                pass # Sometimes it's not needed, fail silently

        # Timezone Handling (Robust)
        if stock_df.index.tz is None:
            stock_df.index = stock_df.index.tz_localize("UTC").tz_convert("Asia/Taipei")
        else:
            stock_df.index = stock_df.index.tz_convert("Asia/Taipei")

        # Reset index to make 'Time' a column for plotting
        stock_df.reset_index(inplace=True)
        # Standardize column name to 'Time'
        if 'Datetime' in stock_df.columns:
            stock_df.rename(columns={'Datetime': 'Time'}, inplace=True)
        elif 'Date' in stock_df.columns:
            stock_df.rename(columns={'Date': 'Time'}, inplace=True)

        # Calculate VWAP
        # Formula: Cumulative(Typical Price * Vol) / Cumulative(Vol)
        # Handle cases where Volume is 0 to avoid division by zero
        v = stock_df['Volume'].replace(0, 1) 
        tp = (stock_df['High'] + stock_df['Low'] + stock_df['Close']) / 3
        stock_df['VWAP'] = (tp * v).cumsum() / v.cumsum()

        # --- 2. Fetch Index Data (^TWII) ---
        # Try fetching 1m data for Index. 
        # Note: ^TWII data availability on Yahoo is sometimes spotty for intraday.
        index_df = yf.download("^TWII", start=start_str, end=end_str, interval="1m", progress=False, auto_adjust=True)

        if not index_df.empty:
            if isinstance(index_df.columns, pd.MultiIndex):
                try:
                    index_df.columns = index_df.columns.droplevel(1)
                except:
                    pass
            
            if index_df.index.tz is None:
                index_df.index = index_df.index.tz_localize("UTC").tz_convert("Asia/Taipei")
            else:
                index_df.index = index_df.index.tz_convert("Asia/Taipei")
                
            index_df.reset_index(inplace=True)
            if 'Datetime' in index_df.columns:
                index_df.rename(columns={'Datetime': 'Time'}, inplace=True)

        return stock_df, index_df

    except Exception as e:
        log_error(e, f"get_real_data for {ticker} on {date_str}")
        # Return empty DFs so the UI handles it gracefully (e.g. shows error) rather than crashing
        return pd.DataFrame(), pd.DataFrame()
