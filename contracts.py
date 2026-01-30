# contracts.py
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class RiskRequest:
    engine: str
    action: str
    suggested_leverage: float
    volatility_ratio: float
    estimated_risk: float


@dataclass
class TradeIntent:
    engine: str
    action: str
    trade_side: str
    pos_side: str
    size: float
    margin_mode: str
    risk_request: RiskRequest
    client_oid: Optional[str] = None
    approved_leverage: Optional[float] = None


@dataclass
class MarketData:
    price: float
    ema20: Optional[float]
    atr: Optional[float]
    rsi: Optional[float]
    vol_ratio: Optional[float]
    ts: float


@dataclass
class StrategySnapshot:
    account: Optional["Account"]
    positions: Dict[str, "Position"]
    position_uncertain: bool


@dataclass
class RiskSnapshot:
    wallet_balance: float
    trend_float: float
    shark_float: float
    margin_usage: float
    timestamp: float


@dataclass
class StrategyContext:
    market_data: MarketData
    account_snapshot: StrategySnapshot
    system_mode: str
    risk_regime: str
    state_confidence: Optional[float]


@dataclass
class RawPosition:
    symbol: str
    side: str
    size: float
    entry_price: float
    unrealized_pnl: float
    leverage: float
    margin: float
    timestamp: float


@dataclass
class RawAccount:
    equity: float
    wallet_balance: float
    available_balance: float
    margin_ratio: float
    timestamp: float


@dataclass
class DataSnapshot:
    positions: Dict[str, RawPosition]
    account: Optional[RawAccount]
    position_uncertain: bool
    timestamp: float


@dataclass
class Position:
    side: str
    size: float
    entry_price: float
    unrealized_pnl: float
    leverage: float
    margin: float
    notional_value: float = 0.0


@dataclass
class Account:
    equity: float
    wallet_balance: float
    available_balance: float
    margin_ratio: float
    total_unrealized_pnl: float = 0.0
    used_margin: float = 0.0
    margin_usage: float = 0.0
