# market_data_hub.py
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock

from contracts import MarketData

@dataclass
class Candle:
    ts: float
    o: float
    h: float
    l: float
    c: float
    v: float

class MarketDataHub:
    def __init__(self, max_candles: int = 500):
        self._lock = Lock()
        self._candles = deque(maxlen=max_candles)
        self._latest_price = None
        self._latest_ts = 0.0

        self._ema20 = None
        self._atr14 = None
        self._rsi14 = None
        self._vol_ratio = None

    def update_ticker(self, ticker_item: dict):
        last = ticker_item.get("lastPr") or ticker_item.get("last") or ticker_item.get("close")
        if last is None:
            return
        with self._lock:
            self._latest_price = float(last)
            self._latest_ts = time.time()

    def update_candles(self, candle_rows: list):
        parsed = []
        for row in candle_rows:
            if not row or len(row) < 6:
                continue
            ts_raw = float(row[0])
            ts = ts_raw / 1000.0 if ts_raw > 1e12 else ts_raw
            parsed.append(Candle(ts, float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])))

        if not parsed:
            return

        with self._lock:
            existing_ts = {c.ts for c in self._candles}
            for c in parsed:
                if c.ts not in existing_ts:
                    self._candles.append(c)

            self._latest_price = self._candles[-1].c
            self._latest_ts = time.time()
            self._recalc_indicators()

    def _recalc_indicators(self):
        closes = [c.c for c in self._candles]
        highs  = [c.h for c in self._candles]
        lows   = [c.l for c in self._candles]
        vols   = [c.v for c in self._candles]

        # EMA20
        if len(closes) >= 20:
            k = 2 / (20 + 1)
            ema = closes[0]
            for x in closes[1:]:
                ema = x * k + ema * (1 - k)
            self._ema20 = ema

        # ATR14
        if len(closes) >= 15:
            trs = []
            for i in range(1, len(closes)):
                tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
                trs.append(tr)
            self._atr14 = sum(trs[-14:]) / 14

        # RSI14
        if len(closes) >= 15:
            gains, losses = [], []
            for i in range(1, len(closes)):
                chg = closes[i] - closes[i-1]
                gains.append(max(chg, 0))
                losses.append(max(-chg, 0))
            avg_gain = sum(gains[-14:]) / 14
            avg_loss = sum(losses[-14:]) / 14
            self._rsi14 = 100.0 if avg_loss == 0 else (100 - (100 / (1 + (avg_gain / avg_loss))))

        # vol_ratio：当前量 / 近20均量
        if len(vols) >= 20:
            avgv = sum(vols[-20:]) / 20
            self._vol_ratio = (vols[-1] / avgv) if avgv > 0 else 1.0

    def get_latest(self) -> MarketData | None:
        with self._lock:
            if self._latest_price is None:
                return None
            return MarketData(
                price=self._latest_price,
                ema20=self._ema20,
                atr=self._atr14,
                rsi=self._rsi14,
                vol_ratio=self._vol_ratio,
                ts=self._latest_ts,
            )
