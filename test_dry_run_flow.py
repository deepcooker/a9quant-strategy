import asyncio
import time

from contracts import MarketData, StrategyContext, StrategySnapshot
from advanced_risk import RiskManager
from trend_engine import TrendEngine
from tiny_oms import TinyOMS


class DummyTrader:
    exchange_id = "bitget"


async def main():
    print("🧪 Dry-run 全链路测试开始")
    class DummyDataSync:
        rest_fail_count = 0

    class DummyAccountState:
        data_sync = DummyDataSync()
        state_confidence = 0.9

        def get_strategy_snapshot(self, engine_name: str):
            return StrategySnapshot(account=None, positions={}, position_uncertain=False)

    risk_manager = RiskManager(initial_capital=200, account_state=DummyAccountState())
    trend_engine = TrendEngine(risk_manager)
    oms = TinyOMS(DummyTrader(), "BTC/USDT:USDT", dry_run=True)

    market_data = MarketData(
        price=50000,
        ema20=49000,
        atr=500,
        rsi=75,
        vol_ratio=1.0,
        ts=time.time(),
    )

    context = StrategyContext(
        market_data=market_data,
        account_snapshot=StrategySnapshot(account=None, positions={}, position_uncertain=False),
        system_mode="NORMAL",
        risk_regime="NORMAL",
        state_confidence=None,
    )

    intent = trend_engine.on_tick(context)
    if not intent:
        raise RuntimeError("未生成交易意图，测试失败")

    ok, lev, msg = risk_manager.approve_action(intent.risk_request)
    if not ok:
        raise RuntimeError(f"风控拒绝: {msg}")
    intent.approved_leverage = lev

    client_oid = await oms.place_intent(intent)
    print(f"✅ Dry-run 下单完成: {client_oid}")


if __name__ == "__main__":
    asyncio.run(main())
