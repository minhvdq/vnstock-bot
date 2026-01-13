from datetime import date
import pandas as pd
import numpy as np
import talib
from vnstock import Quote

# --- 1. CÁC HÀM HỖ TRỢ LOGIC ---

def is_in_range(val_rsi, type='any'):
    """Kiểm tra RSI có nằm trong vùng quá mua/quá bán không"""
    if type == 'bearish': 
        return val_rsi > 65
    if type == 'bullish': 
        return val_rsi < 35
    return val_rsi < 35 or val_rsi > 65

def is_peak(df, i, order=5):
    if i < order or i >= len(df) - order:
        return False
    current_high = df[i]['high'] 
    
    for j in range(i - order, i):
        if df[j]['high'] > current_high:
            return False
    for j in range(i + 1, i + order + 1):
        if df[j]['high'] > current_high:
            return False
    return True

def is_trough(df, i, order=5):
    if i < order or i >= len(df) - order:
        return False
    current_low = df[i]['low'] 
    
    for j in range(i - order, i):
        if df[j]['low'] < current_low:
            return False
    for j in range(i + 1, i + order + 1):
        if df[j]['low'] < current_low:
            return False
    return True

def is_divergence(df, index):
    peaks = []
    troughs = []

    for i in range(len(df)):
        if is_peak(df, i):
            peaks.append(i)
        if is_trough(df, i):
            troughs.append(i)
    bearish_cnt = 0
    bullish_cnt = 0
    if is_peak(df, index):
        for j in range(len(peaks) - 1, -1, -1): 
            old_idx = peaks[j]
            
            distance = index - old_idx
            if distance > 60: break 
            if distance < 10: continue 
            
            if is_in_range(df[index]["RSI"], 'bearish') or is_in_range(df[old_idx]["RSI"], 'bearish'):
                
                if df[index]["high"] > df[old_idx]["high"] and df[index]["RSI"] < df[old_idx]["RSI"]:
                    bearish_cnt += 1
                    if bearish_cnt >= 2:
                        print(f"🔴 [BEARISH] Tìm thấy Phân kỳ ÂM tại dòng {index}")
                        print(f"   - Đỉnh cũ ({df[old_idx]['time']}): Giá {df[old_idx]['high']} | RSI {df[old_idx]['RSI']:.2f}")
                        print(f"   - Đỉnh mới ({df[index]['time']}): Giá {df[index]['high']} | RSI {df[index]['RSI']:.2f}")
                        print("-" * 40)
                        divergence = {
                            "prefixIndex": old_idx,
                            "suffixIndex": index,
                            "type": "bearish"
                        }
                        return divergence                
            
    if is_trough(df, index):
        for j in range(len(troughs) - 1, -1, -1):
            old_idx = troughs[j]
            
            distance = index - old_idx
            if distance > 60: break
            if distance < 10: continue
            
            if is_in_range(df[index]["RSI"], 'bullish') or is_in_range(df[old_idx]["RSI"], 'bullish'):
                
                if df[index]["low"] < df[old_idx]["low"] and df[index]["RSI"] > df[old_idx]["RSI"]:
                    bullish_cnt += 1
                    if bullish_cnt >= 2:
                        print(f"🟢 [BULLISH] Tìm thấy Phân kỳ DƯƠNG tại dòng {index}")
                        print(f"   - Đáy cũ ({df[old_idx]['time']}): Giá {df[old_idx]['low']} | RSI {df[old_idx]['RSI']:.2f}")
                        print(f"   - Đáy mới ({df[index]['time']}): Giá {df[index]['low']} | RSI {df[index]['RSI']:.2f}")
                        print("-" * 40)     
                        divergence = {
                            "prefixIndex": old_idx,
                            "suffixIndex": index,
                            "type": "bullish"
                        }
                        return divergence
    return None

def tim_phan_ky(df):
    n = len(df)
    peaks = []   
    troughs = [] 

    divergences = []  # (prefix index: number, suffix index: number, {bearish or bullish}: enum)
    
    for i in range(n):
        if is_peak(df, i):
            for j in range(len(peaks) - 1, -1, -1): 
                old_idx = peaks[j]
                
                distance = i - old_idx
                if distance > 60: break 
                if distance < 10: continue 
                
                if is_in_range(df[i]["RSI"], 'bearish') or is_in_range(df[old_idx]["RSI"], 'bearish'):
                    
                    if df[i]["high"] > df[old_idx]["high"] and df[i]["RSI"] < df[old_idx]["RSI"]:
                        print(f"🔴 [BEARISH] Tìm thấy Phân kỳ ÂM tại dòng {i}")
                        print(f"   - Đỉnh cũ ({df[old_idx]['time']}): Giá {df[old_idx]['high']} | RSI {df[old_idx]['RSI']:.2f}")
                        print(f"   - Đỉnh mới ({df[i]['time']}): Giá {df[i]['high']} | RSI {df[i]['RSI']:.2f}")
                        print("-" * 40)
                        divergence = {
                            "prefixIndex": old_idx,
                            "suffixIndex": i,
                            "type": "bearish"
                        }
                        divergences.append(divergence)
                        
            peaks.append(i) 
            
        if is_trough(df, i):
            for j in range(len(troughs) - 1, -1, -1):
                old_idx = troughs[j]
                
                distance = i - old_idx
                if distance > 60: break
                if distance < 10: continue
                
                if is_in_range(df[i]["RSI"], 'bullish') or is_in_range(df[old_idx]["RSI"], 'bullish'):
                    
                    if df[i]["low"] < df[old_idx]["low"] and df[i]["RSI"] > df[old_idx]["RSI"]:
                        print(f"🟢 [BULLISH] Tìm thấy Phân kỳ DƯƠNG tại dòng {i}")
                        print(f"   - Đáy cũ ({df[old_idx]['time']}): Giá {df[old_idx]['low']} | RSI {df[old_idx]['RSI']:.2f}")
                        print(f"   - Đáy mới ({df[i]['time']}): Giá {df[i]['low']} | RSI {df[i]['RSI']:.2f}")
                        print("-" * 40)     
                        divergence = {
                            "prefixIndex": old_idx,
                            "suffixIndex": i,
                            "type": "bullish"
                        }
                        divergences.append(divergence)                   
            troughs.append(i) 
        
    return divergences

def get_price_today(symbol: str = 'VGI'):
    quote = Quote(symbol=symbol, source='VCI')
    today = date.today()
    if(today.weekday() == 5 or today.weekday() == 6):
        raise ValueError("Date is not a trading day")
    print(f"Getting price records on {today}...")
    try:
        # records = quote.history(start=today, end=today, interval='1m', to_df=False)
        records = quote.intraday()
        # print("Got records: " + records)
        records_json = records.to_json(orient='records')
        # records_json = records
        # print(records)
        return records_json
    except Exception as e:
        print("Dit me bug " + str(e))
        raise

def get_mock_price(symbol: str = 'VGI'): 
    print("Getting mock data...")

    quote = Quote(symbol=symbol, source='VCI') 
    # df = quote.history(start='2024-05-25', end='2024-05-26', interval='1m') 
    df = quote.intraday(symbol=symbol)
    df['RSI'] = talib.RSI(df['close'], timeperiod=14) 
    df_filtered = df.dropna(subset=['RSI'])
    
    if isinstance(df_filtered.index, pd.DatetimeIndex):
        df_filtered = df_filtered.reset_index()
    
    time_col = next((col for col in ['time', 'Time', 'datetime', 'date'] if col in df_filtered.columns), None)
    if time_col:
        df_filtered['time'] = df_filtered[time_col].astype(str)
    else:
        df_filtered['time'] = df_filtered.index.astype(str)

    records_list = df_filtered.to_dict(orient="records")
    print(f"Data loaded: {len(records_list)} candles.")
    
    divergences = tim_phan_ky(records_list)
    return records_list, divergences
    # return df_filtered

def simulate_trading():
    cur_money = 50000
    amt_stock = 0
    records_list, _= get_mock_price()
    # Convert DataFrame to list of dictionaries for is_divergence function
    # records_list= df.to_dict(orient="records")
    n = len(records_list)
    for i in range(n):
        divergence = is_divergence(records_list, i)
        if divergence is None: continue
        if divergence["type"] == "bullish":
            stock_price = records_list[i]["close"]
            no_stocks = cur_money // stock_price
            total_stock_price = stock_price * no_stocks
            cur_money -= total_stock_price
            amt_stock += no_stocks
        elif divergence["type"] == "bearish":
            stock_price = records_list[i]["close"]
            cur_money += stock_price * amt_stock
            amt_stock = 0
    total_money = cur_money
    if(n > 0):
        total_money += amt_stock * records_list[n - 1]["close"]
    print("End of trading day: ")
    print("Money in the bank: " + str(cur_money))
    print("Number of stock holding: " + str(amt_stock))
    print("current stock price: " + (str(records_list[n - 1]["close"] if n > 0 else 0)))
    print("total value: " + str(total_money))

if __name__ == "__main__":
    # get_mock_price()
    simulate_trading()