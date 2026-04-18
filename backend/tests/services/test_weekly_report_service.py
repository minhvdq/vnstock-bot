from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from app.services.weekly_report_service import build_weekly_report, format_weekly_report


def _make_trade(symbol, strategy, pnl_amount, pnl_pct):
    t = MagicMock()
    t.strategy_name = strategy
    t.symbol = symbol
    t.pnl_amount = pnl_amount
    t.pnl_pct = pnl_pct
    t.exit_time = datetime.now(timezone.utc)
    t.status = MagicMock()
    return t


@patch('app.services.weekly_report_service.SessionLocal')
def test_build_weekly_report_no_trades(mock_session_cls):
    mock_db = MagicMock()
    portfolio = MagicMock()
    portfolio.starting_balance = 100_000_000
    portfolio.available_cash = 100_000_000
    mock_db.query.return_value.filter.return_value.first.return_value = portfolio
    mock_db.query.return_value.filter.return_value.all.return_value = []
    mock_db.query.return_value.filter.return_value.count.return_value = 0
    mock_session_cls.return_value = mock_db

    report = build_weekly_report(user_id=1)

    assert report['total_trades'] == 0
    assert report['total_pnl'] == 0
    assert report['by_strategy'] == {}
    assert report['best_trade'] is None
    assert report['worst_trade'] is None


@patch('app.services.weekly_report_service.SessionLocal')
def test_build_weekly_report_with_trades(mock_session_cls):
    mock_db = MagicMock()
    portfolio = MagicMock()
    portfolio.starting_balance = 100_000_000
    portfolio.available_cash = 80_000_000

    trades = [
        _make_trade('VCB', 'rsi_divergence', 2_000_000, 2.0),
        _make_trade('HPG', 'rsi_divergence', -500_000, -0.5),
        _make_trade('FPT', 'ema_macd', 1_500_000, 1.5),
    ]
    mock_db.query.return_value.filter.return_value.first.return_value = portfolio
    mock_db.query.return_value.filter.return_value.all.return_value = trades
    mock_db.query.return_value.filter.return_value.count.return_value = 2
    mock_session_cls.return_value = mock_db

    report = build_weekly_report(user_id=1)

    assert report['total_trades'] == 3
    assert report['total_pnl'] == 3_000_000
    assert 'rsi_divergence' in report['by_strategy']
    assert report['by_strategy']['rsi_divergence']['trades'] == 2
    assert report['by_strategy']['rsi_divergence']['wins'] == 1
    assert report['by_strategy']['rsi_divergence']['pnl'] == 1_500_000
    assert report['by_strategy']['ema_macd']['trades'] == 1
    assert report['best_trade']['symbol'] == 'VCB'
    assert report['worst_trade']['symbol'] == 'HPG'


def test_format_weekly_report_no_trades():
    report = {
        'period_days': 7,
        'starting_balance': 100_000_000,
        'available_cash': 100_000_000,
        'open_positions': 0,
        'total_pnl': 0,
        'total_trades': 0,
        'by_strategy': {},
        'best_trade': None,
        'worst_trade': None,
    }
    text = format_weekly_report(report)
    assert 'Weekly Paper Trade Report' in text
    assert 'No closed trades' in text


def test_format_weekly_report_with_trades():
    report = {
        'period_days': 7,
        'starting_balance': 100_000_000,
        'available_cash': 85_000_000,
        'open_positions': 1,
        'total_pnl': 3_000_000,
        'total_trades': 3,
        'by_strategy': {
            'rsi_divergence': {'trades': 2, 'wins': 2, 'pnl': 2_000_000},
            'ema_macd': {'trades': 1, 'wins': 0, 'pnl': 1_000_000},
        },
        'best_trade': {'symbol': 'VCB', 'pnl_pct': 2.5},
        'worst_trade': {'symbol': 'HPG', 'pnl_pct': -0.5},
    }
    text = format_weekly_report(report)
    assert 'RSI Divergence' in text
    assert 'EMA+MACD' in text
    assert 'VCB' in text
    assert 'HPG' in text
    assert '+3.00%' in text
