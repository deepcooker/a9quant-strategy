# test_integration.py
import asyncio
import json

from contracts import RiskRequest, StrategySnapshot, TradeIntent
from advanced_risk import RiskManager


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
