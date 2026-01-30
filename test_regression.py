import asyncio
import os
import sys
import types

import pytest

from contracts import DataSnapshot, MarketData, RiskRequest, StrategySnapshot, TradeIntent
from advanced_risk import RiskManager
from account_state import AccountState
from data_synchronizer import DataSynchronizer
from replay_runner import run_replay
from tiny_oms import OrderStatus, TinyOMS, resolve_trade_mode


class DummyExchange:
    def __init__(self):
        self.called = False

    def private_mix_post_v2_mix_order_place_order(self, req):
        self.called = True
        return {"code": "00000", "data": {"orderId": "test"}}


class DummyTrader:
    exchange_id = "bitget"

    def __init__(self, exchange=None):
        self.exchange = exchange


def build_intent(trace_id="trace-test", decision_id="decision-1"):
    risk_request = RiskRequest(
        engine="SHARK",
        action="OPEN_L1",
        suggested_leverage=2,
        volatility_ratio=1.0,
        estimated_risk=1.0,
        trace_id=trace_id,
    )
    return TradeIntent(
        engine="SHARK",
        action="OPEN_L1",
        trade_side="open",
        pos_side="short",
        size=0.01,
        margin_mode="crossed",
        risk_request=risk_request,
        trace_id=trace_id,
        decision_id=decision_id,
    )


def test_live_gate_requires_env_and_config(monkeypatch):
    exchange = DummyExchange()
    intent = build_intent()

    monkeypatch.delenv("ALLOW_LIVE_TRADING", raising=False)
    dry_run, _ = resolve_trade_mode(live_trading_config=True, env_allow=os.getenv("ALLOW_LIVE_TRADING"))
    oms = TinyOMS(DummyTrader(exchange), "BTC/USDT:USDT", dry_run=dry_run)
    asyncio.run(oms.place_intent(intent))
    assert exchange.called is False

    exchange.called = False
    monkeypatch.setenv("ALLOW_LIVE_TRADING", "true")
    dry_run, _ = resolve_trade_mode(live_trading_config=False, env_allow=os.getenv("ALLOW_LIVE_TRADING"))
    oms = TinyOMS(DummyTrader(exchange), "BTC/USDT:USDT", dry_run=dry_run)
    asyncio.run(oms.place_intent(intent))
    assert exchange.called is False

    exchange.called = False
    dry_run, _ = resolve_trade_mode(live_trading_config=True, env_allow=os.getenv("ALLOW_LIVE_TRADING"))
    oms = TinyOMS(DummyTrader(exchange), "BTC/USDT:USDT", dry_run=dry_run)
    asyncio.run(oms.place_intent(intent))
    assert exchange.called is True


def test_trace_id_propagates_to_risk_and_oms():
    class DummyDataSync:
        rest_fail_count = 0

    class DummyAccountState:
        data_sync = DummyDataSync()
        state_confidence = 0.95

        def get_strategy_snapshot(self, engine_name: str):
            return StrategySnapshot(account=None, positions={}, position_uncertain=False)

    rm = RiskManager(initial_capital=200, account_state=DummyAccountState())
    rm.anchor_capital = 200
    rm.update_snapshot(wallet_balance=200, trend_float=0, shark_float=0, margin_usage=0.1)
    from advanced_risk import PolicyDecision, SystemMode, RiskRegime
    rm.evaluate_policy = lambda: PolicyDecision(SystemMode.NORMAL, RiskRegime.NORMAL, ["OPEN"], [], "test", 0.0)

    intent = build_intent(trace_id="trace-prop", decision_id="decision-prop")
    ok, _, _ = rm.approve_action(intent.risk_request)
    assert ok is True
    assert rm.last_decision_trace_id == "trace-prop"

    oms = TinyOMS(DummyTrader(DummyExchange()), "BTC/USDT:USDT", dry_run=True)
    client_oid = asyncio.run(oms.place_intent(intent))
    assert oms.orders[client_oid].trace_id == "trace-prop"


def test_state_is_updated_only_via_synchronizer():
    class DummyTrader:
        exchange_id = "bitget"

    data_sync = DataSynchronizer(DummyTrader(), "BTC/USDT:USDT")
    account_state = AccountState(data_sync)

    account_state.update()
    assert account_state.positions == {}

    mock_ws_data = [
        {
            "instId": "BTCUSDT",
            "holdSide": "long",
            "total": "0.001",
            "openPriceAvg": "60000",
            "unrealizedPL": "15.0",
            "leverage": "3",
            "marginSize": "20.0",
        }
    ]
    data_sync.update_from_ws_position(mock_ws_data)
    account_state.update()
    assert "long" in account_state.positions


def test_oms_idempotency_prevents_duplicate_orders():
    intent = build_intent()
    oms = TinyOMS(DummyTrader(DummyExchange()), "BTC/USDT:USDT", dry_run=True)
    first = asyncio.run(oms.place_intent(intent))
    second = asyncio.run(oms.place_intent(intent))

    assert first == second
    assert len(oms.orders) == 1


def test_dry_run_state_machine_reaches_filled():
    intent = build_intent()
    oms = TinyOMS(DummyTrader(DummyExchange()), "BTC/USDT:USDT", dry_run=True)
    client_oid = asyncio.run(oms.place_intent(intent))
    assert oms.orders[client_oid].status == OrderStatus.FILLED


def test_reconnect_triggers_resubscribe_and_calibration():
    fake_websockets = types.SimpleNamespace(connect=lambda *args, **kwargs: None)
    fake_proxy = types.SimpleNamespace(
        Proxy=types.SimpleNamespace(from_url=lambda *_args, **_kwargs: None),
        proxy_connect=lambda *args, **kwargs: None,
    )
    sys.modules.setdefault("websockets", fake_websockets)
    sys.modules.setdefault("websockets_proxy", fake_proxy)

    from bitget_ws_bridge import BitgetWSBridge

    class DummyDataSync:
        def __init__(self):
            self.calibrations = 0
            self.ws_disconnect_count = 0

        async def calibrate_positions(self):
            self.calibrations += 1
            return True

        async def calibrate_balance(self):
            self.calibrations += 1
            return True

        async def calibrate_orders(self):
            self.calibrations += 1
            return True

        def mark_ws_public_disconnect(self):
            self.ws_disconnect_count += 1

        def mark_ws_private_disconnect(self):
            self.ws_disconnect_count += 1

    class DummyMarketHub:
        def update_ticker(self, *_args, **_kwargs):
            return None

        def update_candles(self, *_args, **_kwargs):
            return None

    data_sync = DummyDataSync()
    bridge = BitgetWSBridge(
        api_key="k",
        secret="s",
        passphrase="p",
        market_hub=DummyMarketHub(),
        data_sync=data_sync,
        oms=None,
    )

    asyncio.run(bridge.on_private_reconnect())
    assert bridge.private_reconnect_count == 1
    assert data_sync.calibrations == 3


def test_replay_drives_full_chain():
    from trend_engine import TrendEngine
    from advanced_risk import RiskManager

    class DummyDataSync:
        position_uncertain = False

        def get_snapshot(self):
            return DataSnapshot(positions={}, account=None, position_uncertain=False, timestamp=0.0)

        def mark_order_sent(self):
            return None

        def report_execution_event(self, *_args, **_kwargs):
            return None

        def is_private_ready(self, *_args, **_kwargs):
            return True

    data_sync = DummyDataSync()
    account_state = AccountState(data_sync)
    risk_manager = RiskManager(initial_capital=200, account_state=account_state)

    class ReplayController:
        def __init__(self):
            self.data_sync = data_sync
            self.account_state = account_state
            self.risk_manager = risk_manager
            self.trend_engine = TrendEngine(self.risk_manager)
            self.shark_engine = None
            self.strategy_registry = {"trend": "ENABLED", "shark": "DISABLED"}
            self.oms = TinyOMS(DummyTrader(DummyExchange()), "BTC/USDT:USDT", data_sync=data_sync, dry_run=True)

        async def process_signals(self, trend_intent, shark_intent):
            intents = []
            if trend_intent:
                intents.append(trend_intent)
            for intent in intents:
                ok, lev, _ = self.risk_manager.approve_action(intent.risk_request)
                assert ok is True
                intent.approved_leverage = lev
                await self.oms.place_intent(intent)

    controller = ReplayController()
    events = [
        MarketData(price=100, ema20=99, atr=1, rsi=65, vol_ratio=1.0, ts=1),
        MarketData(price=101, ema20=99, atr=1, rsi=72, vol_ratio=1.0, ts=2),
        MarketData(price=102, ema20=100, atr=1, rsi=75, vol_ratio=1.0, ts=3),
        MarketData(price=103, ema20=100, atr=1, rsi=74, vol_ratio=1.0, ts=4),
        MarketData(price=104, ema20=101, atr=1, rsi=73, vol_ratio=1.0, ts=5),
    ]

    intents = asyncio.run(run_replay(controller, events))
    assert intents
    assert any(order.status == OrderStatus.FILLED for order in controller.oms.orders.values())


def test_intents_must_go_through_risk_gate():
    class DummyDataSync:
        position_uncertain = False

        def get_snapshot(self):
            return DataSnapshot(positions={}, account=None, position_uncertain=False, timestamp=0.0)

    account_state = AccountState(DummyDataSync())
    risk_manager = RiskManager(initial_capital=200, account_state=account_state)
    oms = TinyOMS(DummyTrader(DummyExchange()), "BTC/USDT:USDT", dry_run=True)

    intent = build_intent(trace_id="risk-check", decision_id="risk-check")
    approved_calls = {"count": 0}

    original_approve = risk_manager.approve_action

    def approve_action(request):
        approved_calls["count"] += 1
        return original_approve(request)

    risk_manager.approve_action = approve_action
    ok, lev, _ = risk_manager.approve_action(intent.risk_request)
    assert ok is True
    intent.approved_leverage = lev
    asyncio.run(oms.place_intent(intent))
    assert approved_calls["count"] == 1
