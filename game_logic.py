import pandas as pd
import numpy as np
import json
import yfinance as yf
import streamlit as st
from logger import log_error
import datetime
from datetime import timedelta

EXAMS_FILE = "exams.json"

def load_exam_data(filepath=EXAMS_FILE):
    try:
        with open(filepath, "r", encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        log_error(e, "load_exam_data")
        return []

def filter_questions(data, mode):
    # If mode is Realistic, return Real questions.
    # If mode matches 'Real', return Real.
    if mode == "Realistic" or mode == "Real":
        return [q for q in data if q.get("level") == "Real"]
    # Fallback for other modes if they exist in JSON
    return [q for q in data if q.get("level") == mode]

@st.cache_data(ttl=3600) # Cache for 1 hour
def get_real_data(ticker, date_str):
    """
    Fetches 1m data for the specific ticker and market index (^TWII) for the given date.
    Returns (stock_df, index_df).
    """
    try:
        start_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        end_date = start_date + datetime.timedelta(days=1)
        
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        # 1. Fetch Stock Data
        stock_df = yf.download(ticker, start=start_str, end=end_str, interval="1m", progress=False)
        
        if stock_df.empty:
            # Try fetching with period="1d" if start/end fails (sometimes yfinance is finicky)
            # But period="1d" gets today's data. We need historical.
            # If empty, maybe date is > 30 days ago.
            return pd.DataFrame(), pd.DataFrame()

        # Handle MultiIndex
        if isinstance(stock_df.columns, pd.MultiIndex):
            stock_df.columns = stock_df.columns.droplevel(1)

        # Localize if needed
        if stock_df.index.tz is None:
             stock_df.index = stock_df.index.tz_localize("UTC").tz_convert("Asia/Taipei")
        else:
             stock_df.index = stock_df.index.tz_convert("Asia/Taipei")

        # Calculate VWAP
        stock_df['Typical_Price'] = (stock_df['High'] + stock_df['Low'] + stock_df['Close']) / 3
        stock_df['VWAP'] = (stock_df['Typical_Price'] * stock_df['Volume']).cumsum() / stock_df['Volume'].cumsum()

        # 2. Fetch Index Data (^TWII)
        # ^TWII often has delayed data or might not support 1m.
        # If 1m fails, try 5m or 1h? But we want alignment.
        # Let's try 1m.
        index_df = yf.download("^TWII", start=start_str, end=end_str, interval="1m", progress=False)

        if not index_df.empty:
            if isinstance(index_df.columns, pd.MultiIndex):
                index_df.columns = index_df.columns.droplevel(1)
            if index_df.index.tz is None:
                 index_df.index = index_df.index.tz_localize("UTC").tz_convert("Asia/Taipei")
            else:
                 index_df.index = index_df.index.tz_convert("Asia/Taipei")

        # Reset index to allow merging/plotting easily or keep DatetimeIndex
        stock_df.reset_index(inplace=True)
        # Rename 'Datetime' to 'Time' for compatibility
        if 'Datetime' in stock_df.columns:
            stock_df.rename(columns={'Datetime': 'Time'}, inplace=True)
            
        if not index_df.empty:
            index_df.reset_index(inplace=True)
            if 'Datetime' in index_df.columns:
                index_df.rename(columns={'Datetime': 'Time'}, inplace=True)

        return stock_df, index_df

    except Exception as e:
        log_error(e, f"get_real_data for {ticker} on {date_str}")
        return pd.DataFrame(), pd.DataFrame()
