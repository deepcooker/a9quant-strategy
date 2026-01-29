# test_data_flow.py
from .ccxt_utils import ExchangeTrader
from .data_synchronizer import DataSynchronizer
from .account_state import AccountState

# 1. 初始化
trader = ExchangeTrader(...)
data_sync = DataSynchronizer(trader, "BTC/USDT:USDT")
account_state = AccountState(data_sync)

# 2. 手动触发一次REST同步
import asyncio
asyncio.run(data_sync.force_rest_sync())

# 3. 更新并查看状态
account_state.update()
print("风控快照:", account_state.get_risk_snapshot())
print("策略快照:", account_state.get_strategy_snapshot('trend'))