from datetime import date
import pandas as pd
import numpy as np
import talib
from vnstock import Trading, Quote

def get_price_today(symbol: str = 'VGI'):
    quote = Quote(symbol=symbol, source='VCI')
    today = date.today()
    if(today.weekday() == 5 or today.weekday() == 6):
        raise ValueError("Date is not a trading day")
    print(f"Getting price records on {today}...")
    records = quote.history(start=today, end=today, to_df=False)
    # print(type(records))
    records_json = records.to_json(orient='records')
    print(records)
    return records_json

def get_mock_price(): 
    print("getting mock data")
    quote = Quote(symbol='VGI', source='VCI')
    df = quote.history(start='2025-12-04', end='2025-12-04', interval='1m')
    df['RSI'] = talib.RSI(df['close'], timeperiod=6)
    df_filtered = df.dropna(subset=['RSI'])
    
    # Ensure time column is properly formatted
    # Check common time column names and convert to ISO format
    time_col = None
    for col in ['time', 'Time', 'datetime', 'datetime', 'date', 'Date', 'time_string']:
        if col in df_filtered.columns:
            time_col = col
            break
    
    # If index is a DatetimeIndex, use it
    if isinstance(df_filtered.index, pd.DatetimeIndex):
        df_filtered = df_filtered.reset_index()
        if 'index' in df_filtered.columns:
            df_filtered['time'] = df_filtered['index'].dt.strftime('%Y-%m-%d %H:%M:%S')
        time_col = 'time'
    
    # If we found a time column, ensure it's a string in ISO format
    if time_col:
        try:
            # Try to convert to datetime and format
            df_filtered['time'] = pd.to_datetime(df_filtered[time_col], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
            # Fill any NaT values (failed conversions) with original string
            mask = df_filtered['time'].isna()
            if mask.any():
                df_filtered.loc[mask, 'time'] = df_filtered.loc[mask, time_col].astype(str)
        except Exception as e:
            print(f"Warning: Could not parse time column {time_col}: {e}")
            # Fallback to string conversion
            if 'time' not in df_filtered.columns:
                df_filtered['time'] = df_filtered[time_col].astype(str)
    
    # Convert DataFrame to list of dictionaries
    records_list = df_filtered.to_dict(orient="records")
    print(f"Returning {len(records_list)} records")
    print(f"Time column: {time_col}")
    print(f"Sample record keys: {list(records_list[0].keys()) if records_list else 'no data'}")
    print(f"Sample time value: {records_list[0].get('time', records_list[0].get(time_col, 'N/A')) if records_list else 'N/A'}")
    tim_phan_ky(records_list)
    return records_list

def tim_phan_ky(df):
    n = len(df)
    peaks = []

    for i in range(n):
        if is_peak(df, i):
            for j in range(len(peaks - 1), -1, -1):
                if i - peaks[j] > 60:
                    break
                if i - peaks[j] > 11:
                    if is_in_range(df[i]["RSI"]) or is_in_range(df[peaks[j]]["RSI"]):
                        if df[i]["RSI"] > df[peaks[j]]["RSI"] and df[i]["close"] < df[peaks[j]]["close"]:
                            print("Found a Bullish Divergence")
                            print(f"Time: {df[peaks[j]]["time"]} - Price: {df[peaks[j]]["close"]} - RSI: {df[peaks[j]]["RSI"]}")
                            print(f"Time: {df[i]["time"]} - Price: {df[i]["close"]} - RSI: {df[i]["RSI"]}")
                        if df[i]["RSI"] < df[peaks[j]]["RSI"] and df[i]["close"] > df[peaks[j]]["close"]:
                            print("Found a Bearish Divergence")
                            print(f"Time: {df[peaks[j]]["time"]} - Price: {df[peaks[j]]["close"]} - RSI: {df[peaks[j]]["RSI"]}")
                            print(f"Time: {df[i]["time"]} - Price: {df[i]["close"]} - RSI: {df[i]["RSI"]}")
            peaks.append(i)

def is_in_range(val):
    return val < 35 or val > 65

def is_peak(df, i):
    for j in range(i-1, max(i-6, -1), -1):
        if df[j]["close"] > df[i]["close"]:
            return False
    for j in range(i + 1, min(i + 6, len(df))):
        if df[j]["close"] > df[i]["close"]:
            return False
    return True