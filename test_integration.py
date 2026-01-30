# test_integration.py
import asyncio
import json

import os


from contracts import RiskRequest, StrategySnapshot, TradeIntent
from advanced_risk import RiskManager
from account_state import AccountState
from data_synchronizer import DataSynchronizer
from tiny_oms import TinyOMS, resolve_trade_mode


def test_risk_reject_reason():
    class DummyDataSync:
        rest_fail_count = 0

    class DummyAccountState:
        data_sync = DummyDataSync()
        state_confidence = 0.95

        def get_strategy_snapshot(self, engine_name: str):
            return StrategySnapshot(account=None, positions={}, position_uncertain=False)

    rm = RiskManager(initial_capital=200, account_state=DummyAccountState())
    rm.update_snapshot(wallet_balance=200, trend_float=0, shark_float=0, margin_usage=0.1)

    request = RiskRequest(
        engine="SHARK",
        action="OPEN_L1",
        suggested_leverage=2,
        volatility_ratio=1.0,
        estimated_risk=1e6,
    )
    intent = TradeIntent(
        engine="SHARK",
        action="OPEN_L1",
        trade_side="open",
        pos_side="short",
        size=1e9,
        margin_mode="crossed",
        risk_request=request,
    )
    ok, _, msg = rm.approve_action(intent.risk_request)
    assert ok is False
    assert msg


async def manual_integration_check():
    from main_controller import MainController
    with open('config.json', 'r') as f:
        config = json.load(f)
    controller = MainController(config)
    # 测试初始化
    print("✅ 主控制器创建成功")
    # 测试一次手动更新
    await controller.data_sync.force_rest_sync()
    controller.account_state.update()
    controller.risk_manager.update_from_account_state()
    print("✅ 风控状态已更新:", controller.risk_manager.realized_profit)


if __name__ == "__main__":
    asyncio.run(manual_integration_check())


class DummyExchange:
    def __init__(self):
        self.called = False

    def private_mix_post_v2_mix_order_place_order(self, req):
        self.called = True
        return {"code": "00000", "data": {"orderId": "test"}}


class DummyTrader:
    exchange_id = "bitget"

    def __init__(self, exchange):
        self.exchange = exchange


def build_intent():
    trace_id = "trace-test"
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
    )


def test_live_gate_requires_env_and_config(monkeypatch):
    exchange = DummyExchange()
    intent = build_intent()

    # config true, env missing -> dry-run
    monkeypatch.delenv("ALLOW_LIVE_TRADING", raising=False)
    dry_run, _ = resolve_trade_mode(live_trading_config=True, env_allow=os.getenv("ALLOW_LIVE_TRADING"))
    oms = TinyOMS(DummyTrader(exchange), "BTC/USDT:USDT", dry_run=dry_run)
    asyncio.run(oms.place_intent(intent))
    assert exchange.called is False

    # env true, config false -> dry-run
    exchange.called = False
    monkeypatch.setenv("ALLOW_LIVE_TRADING", "true")
    dry_run, _ = resolve_trade_mode(live_trading_config=False, env_allow=os.getenv("ALLOW_LIVE_TRADING"))
    oms = TinyOMS(DummyTrader(exchange), "BTC/USDT:USDT", dry_run=dry_run)
    asyncio.run(oms.place_intent(intent))
    assert exchange.called is False

    # both true -> live
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
    rm.update_snapshot(wallet_balance=200, trend_float=0, shark_float=0, margin_usage=0.1)

    trace_id = "trace-prop"
    risk_request = RiskRequest(
        engine="SHARK",
        action="OPEN_L1",
        suggested_leverage=2,
        volatility_ratio=1.0,
        estimated_risk=1.0,
        trace_id=trace_id,
    )
    intent = TradeIntent(
        engine="SHARK",
        action="OPEN_L1",
        trade_side="open",
        pos_side="short",
        size=0.01,
        margin_mode="crossed",
        risk_request=risk_request,
        trace_id=trace_id,
    )

    ok, _, _ = rm.approve_action(intent.risk_request)
    assert ok is True
    assert rm.last_decision_trace_id == trace_id

    exchange = DummyExchange()
    oms = TinyOMS(DummyTrader(exchange), "BTC/USDT:USDT", dry_run=True)
    client_oid = asyncio.run(oms.place_intent(intent))
    assert oms.orders[client_oid].trace_id == trace_id


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
    exchange = DummyExchange()
    intent = build_intent()
    intent.decision_id = "decision-1"

    oms = TinyOMS(DummyTrader(exchange), "BTC/USDT:USDT", dry_run=True)
    first = asyncio.run(oms.place_intent(intent))
    second = asyncio.run(oms.place_intent(intent))

    assert first == second
    assert len(oms.orders) == 1
