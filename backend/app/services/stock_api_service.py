from datetime import date
import talib
from vnstock import Quote
from app.algorithms.rsi_divergence import _find_divergences


def get_price_today(symbol: str = 'VGI'):
    quote = Quote(symbol=symbol, source='VCI')
    today = date.today()
    if today.weekday() in (5, 6):
        raise ValueError('Date is not a trading day')
    print(f'Getting price records on {today}...')
    try:
        records = quote.intraday()
        return records.to_json(orient='records')
    except Exception as e:
        print(f'Error fetching price today: {e}')
        raise


def get_mock_price(symbol: str = 'VGI'):
    print('Getting mock data...')
    quote = Quote(symbol=symbol, source='VCI')
    df = quote.intraday(symbol=symbol)
    df['RSI'] = talib.RSI(df['close'], timeperiod=14)
    df_filtered = df.dropna(subset=['RSI']).reset_index(drop=True)

    time_col = next((c for c in ['time', 'Time', 'datetime', 'date'] if c in df_filtered.columns), None)
    df_filtered['time'] = df_filtered[time_col].astype(str) if time_col else df_filtered.index.astype(str)

    records_list = df_filtered.to_dict(orient='records')
    print(f'Data loaded: {len(records_list)} candles.')
    divergences = _find_divergences(records_list)
    return records_list, divergences
