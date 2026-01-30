import asyncio
import time
from typing import Iterable, List

from contracts import MarketData, StrategyContext
from typing import Any


async def run_replay(controller: Any, events: Iterable[MarketData]) -> List[str]:
    """Drive the full chain using replayed market events."""
    intents: List[str] = []
    for event in events:
        if event.ts is None:
            event.ts = time.time()

        policy = controller.risk_manager.evaluate_policy()
        context = StrategyContext(
            market_data=event,
            account_snapshot=controller.account_state.get_strategy_snapshot("trend"),
            system_mode=policy.system_mode.value,
            risk_regime=policy.risk_regime.value,
            state_confidence=getattr(controller.account_state, "state_confidence", None),
            trace_id=f"replay-{int(time.time()*1000)}",
        )

        trend_intent = None
        shark_intent = None
        if controller.strategy_registry.get("trend") == "ENABLED":
            trend_intent = controller.trend_engine.on_tick(context)
            if trend_intent:
                intents.append(trend_intent.action)

        if controller.strategy_registry.get("shark") == "ENABLED":
            shark_intent = controller.shark_engine.on_tick(context)
            if shark_intent:
                intents.append(shark_intent.action)

        await controller.process_signals(trend_intent, shark_intent)
        await asyncio.sleep(0)
    return intents
