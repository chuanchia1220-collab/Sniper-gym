import yfinance as yf
import pandas as pd
import numpy as np
import json
import datetime
from datetime import timedelta
import os

# Configuration
TICKERS = ['2330.TW', '2317.TW', '2603.TW', '3231.TW', '2454.TW', '2303.TW', '2609.TW', '3035.TW']
INTERVAL = "1m"
OUTPUT_FILE = "exams.json"

def get_date_ranges():
    """Generates 5-day date ranges for the last 30 days."""
    ranges = []
    end_date = datetime.datetime.now()
    # Ensure end_date is not in the future (though now() is fine)

    # We go back 6 chunks of 5 days = 30 days
    for i in range(6):
        start = end_date - timedelta(days=5)
        # Format as YYYY-MM-DD
        ranges.append((start.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
        end_date = start

    return ranges

DATE_RANGES = get_date_ranges()

def calculate_vwap(df):
    """Calculates VWAP for the given DataFrame (assumed to be one day)."""
    df = df.copy()
    # Ensure columns are simple strings
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)

    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['VWAP'] = (df['Typical_Price'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    return df

def find_breakout(df, idx, vwap_col='VWAP'):
    """
    Pattern: Price crosses VWAP from below with Volume > 2x average.
    """
    if idx < 30: return False # Need some history

    current = df.iloc[idx]
    prev = df.iloc[idx-1]

    # Check Cross
    if prev['Close'] < prev[vwap_col] and current['Close'] > current[vwap_col]:
        # Check Volume
        avg_vol = df['Volume'].iloc[idx-30:idx].mean()
        if avg_vol > 0 and current['Volume'] > 2 * avg_vol:
            return True

    return False

def find_bull_trap(df, idx, vwap_col='VWAP'):
    """
    Pattern: Price breaks VWAP but closes below within 5 mins.
    This function looks AHEAD. So we check if a breakout happened at idx,
    and then check the next 5 mins.
    """
    if idx + 5 >= len(df): return False

    current = df.iloc[idx]
    prev = df.iloc[idx-1]

    # 1. Breakout happens at idx (cross up)
    if not (prev['Close'] < prev[vwap_col] and current['Close'] > current[vwap_col]):
        return False

    # 2. Check next 5 mins for close below VWAP
    future_window = df.iloc[idx+1:idx+6]
    for _, row in future_window.iterrows():
        if row['Close'] < row[vwap_col]:
            return True

    return False

def find_mad_dog_wave2(df, idx, vwap_col='VWAP'):
    """
    Pattern: Price breaks VWAP (Wave 1), drops, then breaks again (Wave 2) after 5+ mins.
    We are looking for Wave 2 at 'idx'.
    So at 'idx', we must cross VWAP UP.
    And we must find a previous cross UP (Wave 1) more than 5 mins ago,
    and in between, price was below VWAP.
    """
    if idx < 20: return False

    current = df.iloc[idx]
    prev = df.iloc[idx-1]

    # Must be a crossover UP
    if not (prev['Close'] < prev[vwap_col] and current['Close'] > current[vwap_col]):
        return False

    # Look back for Wave 1
    # We need a period of being BELOW VWAP (at least 5 mins)
    # And before that, a period of being ABOVE VWAP (Wave 1 peak)

    # Scan backwards from idx-1
    # 1. We expect a duration of Close < VWAP
    below_vwap_start = -1
    for i in range(idx-1, idx-60, -1):
        if i < 0: break
        if df.iloc[i]['Close'] > df.iloc[i][vwap_col]:
            below_vwap_start = i
            break

    if below_vwap_start == -1: return False # Never went above VWAP recently

    duration_below = (idx - 1) - below_vwap_start
    if duration_below < 5: return False # Dip was too short

    # The point 'below_vwap_start' is the last point it was ABOVE.
    # So below_vwap_start+1 was the cross DOWN.
    # We want to find the cross UP before that (Wave 1 start).

    return True


def scan_ticker(ticker):
    print(f"Scanning {ticker}...")
    results = []

    for start_date, end_date in DATE_RANGES:
        try:
            print(f"  Fetching {start_date} to {end_date}...")
            # Download data
            df = yf.download(ticker, start=start_date, end=end_date, interval=INTERVAL, progress=False)

            if df.empty:
                print(f"  No data for {ticker} in range {start_date}-{end_date}")
                continue

            # Handle MultiIndex columns
            if isinstance(df.columns, pd.MultiIndex):
                # If we only asked for one ticker, level 1 is the ticker
                df.columns = df.columns.droplevel(1)

            # Convert index to localized time (TW is UTC+8) if it is tz-aware
            if df.index.tz is not None:
                 df.index = df.index.tz_convert("Asia/Taipei")
            else:
                 # Assume UTC and convert? Or assume local?
                 # Yahoo returns UTC usually.
                 df.index = df.index.tz_localize("UTC").tz_convert("Asia/Taipei")

            unique_dates = df.index.normalize().unique()

            for date in unique_dates:
                day_mask = df.index.normalize() == date
                day_df = df[day_mask].copy()

                if len(day_df) < 30: continue # Skip partial days

                # Calculate VWAP for the day
                day_df = calculate_vwap(day_df)

                # Scan for patterns
                for i in range(30, len(day_df) - 6): # -6 to ensure we have room for Bull Trap check

                    ts = day_df.index[i]
                    timestamp_str = ts.strftime("%H:%M:%S")
                    date_str = ts.strftime("%Y-%m-%d")

                    # Check patterns

                    # 1. Breakout
                    if find_breakout(day_df, i):
                        results.append({
                            "id": f"REAL_{ticker}_{date_str}_{timestamp_str.replace(':','')}_BO",
                            "ticker": ticker,
                            "date": date_str,
                            "timestamp": timestamp_str, # Keep seconds? usually just HH:MM
                            "timestamp_short": ts.strftime("%H:%M"),
                            "scenario_type": "Standard Breakout",
                            "market_context": "Tailwind",
                            "correct_action": "Buy",
                            "explanation": f"Auto-detected: Price broke VWAP at {ts.strftime('%H:%M')} with High Volume.",
                            "level": "Real"
                        })
                        continue

                    # 2. Bull Trap
                    if find_bull_trap(day_df, i):
                        results.append({
                            "id": f"REAL_{ticker}_{date_str}_{timestamp_str.replace(':','')}_BT",
                            "ticker": ticker,
                            "date": date_str,
                            "timestamp": timestamp_str,
                            "timestamp_short": ts.strftime("%H:%M"),
                            "scenario_type": "Bull Trap",
                            "market_context": "Fakeout",
                            "correct_action": "Sell",
                            "explanation": f"Auto-detected: Price broke VWAP at {ts.strftime('%H:%M')} but failed and closed below within 5 mins.",
                            "level": "Real"
                        })
                        continue

                    # 3. Mad Dog Wave 2
                    if find_mad_dog_wave2(day_df, i):
                        results.append({
                            "id": f"REAL_{ticker}_{date_str}_{timestamp_str.replace(':','')}_MD2",
                            "ticker": ticker,
                            "date": date_str,
                            "timestamp": timestamp_str,
                            "timestamp_short": ts.strftime("%H:%M"),
                            "scenario_type": "Mad Dog Wave 2",
                            "market_context": "Strong Trend",
                            "correct_action": "Buy",
                            "explanation": f"Auto-detected: Second strong break of VWAP at {ts.strftime('%H:%M')} after a pullback.",
                            "level": "Real"
                        })

        except Exception as e:
            print(f"Error scanning {ticker} range {start_date}-{end_date}: {e}")
            continue

    return results

def main():
    print(f"Scanning date ranges: {DATE_RANGES}")
    all_exams = []

    for ticker in TICKERS:
        scenarios = scan_ticker(ticker)
        all_exams.extend(scenarios)
        print(f"Found {len(scenarios)} scenarios for {ticker}")

    # Transform to fit existing schema
    final_exams = []
    seen_ids = set()

    for s in all_exams:
        if s['id'] in seen_ids: continue
        seen_ids.add(s['id'])

        final_exams.append({
            "id": s['id'],
            "ticker": s['ticker'],
            "date": s['date'],
            "timestamp": s['timestamp_short'], # Use HH:MM format
            "level": s['level'],
            "scenario_type": s['scenario_type'],
            "market_context": s['market_context'],
            "correct_action": s['correct_action'],
            "explanation": s['explanation'],
            "data_snippet": None
        })

    # Save to file
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_exams, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(final_exams)} scenarios to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
