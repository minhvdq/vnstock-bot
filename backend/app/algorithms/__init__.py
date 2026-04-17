from app.algorithms.rsi_divergence import RSIStrategy
from app.algorithms.ema_macd import EMAMACDStrategy
from app.algorithms.donchian_breakout import DonchianStrategy
from app.algorithms.volume_breakout import VolumeBreakoutStrategy

STRATEGIES: dict = {
    "rsi_divergence":    RSIStrategy,
    "ema_macd":          EMAMACDStrategy,
    "donchian_breakout": DonchianStrategy,
    "volume_breakout":   VolumeBreakoutStrategy,
}
