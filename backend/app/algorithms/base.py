from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class Trade:
    action: str               # "buy" | "sell"
    date: str
    price: float
    shares: int
    pnl: Optional[float] = None  # None on buy; realized P&L on sell


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_value: float
    pnl: float          # final_value - initial_capital
    pnl_pct: float      # pnl / initial_capital * 100
    win_rate: float     # % of completed sell trades where pnl > 0
    max_drawdown: float # worst peak-to-trough % loss (negative number)
    total_trades: int   # number of completed buy+sell pairs
    trades: list = field(default_factory=list)  # List[Trade]


class BaseStrategy(ABC):

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add a 'signal' column to df:
          1  = buy
         -1  = sell
          0  = hold
        Return the annotated DataFrame.
        """

    def backtest(
        self,
        df: pd.DataFrame,
        symbol: str,
        initial_capital: float = 100_000_000,
    ) -> BacktestResult:
        """
        Shared simulation loop — identical for all strategies.
        Calls generate_signals() internally, then iterates signals to track
        position, capital, drawdown, and trade log.
        """
        df = self.generate_signals(df.copy())

        capital = initial_capital
        shares = 0
        trades: list[Trade] = []
        peak_value = initial_capital
        max_drawdown = 0.0

        for _, row in df.iterrows():
            signal = int(row.get('signal', 0))
            price = float(row['close'])
            date = str(row.get('time', ''))

            if signal == 1 and shares == 0:
                shares = int(capital // price)
                if shares > 0:
                    capital -= shares * price
                    trades.append(Trade(action='buy', date=date, price=price, shares=shares))

            elif signal == -1 and shares > 0:
                proceeds = shares * price
                cost_basis = trades[-1].price * shares
                realized_pnl = proceeds - cost_basis
                capital += proceeds
                trades.append(Trade(action='sell', date=date, price=price, shares=shares, pnl=realized_pnl))
                shares = 0

            current_value = capital + shares * price
            if current_value > peak_value:
                peak_value = current_value
            drawdown = (current_value - peak_value) / peak_value * 100 if peak_value > 0 else 0.0
            if drawdown < max_drawdown:
                max_drawdown = drawdown

        # Value any open position at last close price
        final_value = capital
        if shares > 0 and len(df) > 0:
            final_value += shares * float(df.iloc[-1]['close'])

        # Metrics from completed buy+sell pairs only
        completed = [
            (trades[i], trades[i + 1])
            for i in range(0, len(trades) - 1, 2)
            if trades[i].action == 'buy' and trades[i + 1].action == 'sell'
        ]
        total_trades = len(completed)
        winning = sum(1 for _, sell in completed if (sell.pnl or 0) > 0)
        win_rate = (winning / total_trades * 100) if total_trades > 0 else 0.0
        pnl = final_value - initial_capital
        pnl_pct = pnl / initial_capital * 100 if initial_capital > 0 else 0.0

        start_date = str(df.iloc[0].get('time', df.index[0])) if len(df) > 0 else ''
        end_date = str(df.iloc[-1].get('time', df.index[-1])) if len(df) > 0 else ''

        return BacktestResult(
            symbol=symbol,
            strategy=self.__class__.__name__,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_value=final_value,
            pnl=pnl,
            pnl_pct=pnl_pct,
            win_rate=win_rate,
            max_drawdown=max_drawdown,
            total_trades=total_trades,
            trades=trades,
        )
